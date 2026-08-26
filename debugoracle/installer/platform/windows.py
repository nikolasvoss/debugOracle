from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from types import ModuleType
from collections.abc import Iterator
import ctypes


@dataclass(frozen=True, slots=True)
class WindowsPathRecord:
    entry: str
    committed: bool = True


@dataclass(slots=True)
class WindowsPathPlan:
    bin_dir: Path
    profile_path: Path
    export_line: str


@dataclass(slots=True)
class PathCleanupResult:
    applied: bool
    marker_found: bool
    legacy_line_found: bool
    manual_action: str | None = None
    error: str | None = None


def build_path_plan(
    bin_dir: Path,
    _shell: str | None,
    home: Path,
    env: Mapping[str, str] | None = None,
) -> WindowsPathPlan:
    resolved_env = env or os.environ
    state_home = Path(
        resolved_env.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
    )
    return WindowsPathPlan(
        bin_dir=bin_dir,
        profile_path=state_home / "DebugOracle" / "installer-managed-path.json",
        export_line=str(bin_dir),
    )


def path_contains(bin_dir: Path, path_value: str | None) -> bool:
    if not path_value:
        return False
    target = str(bin_dir).casefold()
    return any(part.casefold() == target for part in path_value.split(";") if part)


def append_path_line(record_path: Path, entry: str) -> tuple[bool, str | None]:
    try:
        with _windows_path_mutex():
            return _append_path_line_locked(record_path, entry)
    except (OSError, RuntimeError) as error:
        return False, str(error)


def _append_path_line_locked(record_path: Path, entry: str) -> tuple[bool, str | None]:
    try:
        current = _read_user_path()
        if path_contains(Path(entry), current):
            record = load_managed_path_record(record_path)
            if record is not None and record.entry == entry and not record.committed:
                write_managed_path_record(record_path, WindowsPathRecord(entry=entry))
            return True, None
        if _read_user_path() != current:
            raise RuntimeError("Windows user PATH changed before the installer could update it.")
        write_managed_path_record(
            record_path, WindowsPathRecord(entry=entry, committed=False)
        )
        try:
            _write_user_path(_append_entry(current, entry))
        except (OSError, RuntimeError):
            record_path.unlink(missing_ok=True)
            raise
        write_managed_path_record(record_path, WindowsPathRecord(entry=entry))
        return True, None
    except (OSError, RuntimeError) as error:
        return False, str(error)


def cleanup_path_line(
    record_path: Path, entry: str, *, force_legacy: bool = False
) -> PathCleanupResult:
    with _windows_path_mutex():
        return _cleanup_path_line_locked(
            record_path, entry, force_legacy=force_legacy
        )


def _cleanup_path_line_locked(
    record_path: Path, entry: str, *, force_legacy: bool = False
) -> PathCleanupResult:
    del force_legacy
    record = load_managed_path_record(record_path)
    if record is None or not record.committed or record.entry != entry:
        return PathCleanupResult(
            applied=False,
            marker_found=False,
            legacy_line_found=False,
            manual_action="No matching installer-managed Windows PATH entry was found.",
        )
    try:
        current = _read_user_path()
        entries = [part for part in current.split(";") if part]
        matches = [part for part in entries if part.casefold() == entry.casefold()]
        if len(matches) != 1:
            return PathCleanupResult(
                applied=False,
                marker_found=True,
                legacy_line_found=False,
                manual_action="Windows PATH ownership is ambiguous; no PATH entry was removed.",
            )
        _write_user_path(";".join(part for part in entries if part.casefold() != entry.casefold()))
        record_path.unlink(missing_ok=True)
        return PathCleanupResult(applied=True, marker_found=True, legacy_line_found=False)
    except (OSError, RuntimeError) as error:
        return PathCleanupResult(False, True, False, error=str(error))


def load_managed_path_record(record_path: Path) -> WindowsPathRecord | None:
    if not record_path.exists():
        return None
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = payload.get("entry") if isinstance(payload, dict) else None
    committed = payload.get("committed", True) if isinstance(payload, dict) else None
    if not isinstance(entry, str) or not entry:
        return None
    if not isinstance(committed, bool):
        return None
    return WindowsPathRecord(entry=entry, committed=committed)


def write_managed_path_record(record_path: Path, record: WindowsPathRecord) -> None:
    record_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(
        record_path,
        json.dumps(
            {"committed": record.committed, "entry": record.entry}, sort_keys=True
        )
        + "\n",
    )


def _write_text_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _append_entry(current: str, entry: str) -> str:
    return f"{current};{entry}" if current else entry


def _read_user_path() -> str:
    registry = _load_winreg()
    with registry.OpenKey(  # type: ignore[reportAttributeAccessIssue]
        registry.HKEY_CURRENT_USER, "Environment", 0, registry.KEY_READ
    ) as key:  # type: ignore[reportAttributeAccessIssue]
        try:
            value, _value_type = registry.QueryValueEx(key, "Path")  # type: ignore[reportAttributeAccessIssue]
        except FileNotFoundError:
            return ""
    if not isinstance(value, str):
        raise RuntimeError("Windows user PATH is not a string")
    return value


def _write_user_path(value: str) -> None:
    registry = _load_winreg()
    with registry.OpenKey(  # type: ignore[reportAttributeAccessIssue]
        registry.HKEY_CURRENT_USER, "Environment", 0, registry.KEY_SET_VALUE
    ) as key:  # type: ignore[reportAttributeAccessIssue]
        registry.SetValueEx(key, "Path", 0, registry.REG_EXPAND_SZ, value)  # type: ignore[reportAttributeAccessIssue]


def _load_winreg() -> ModuleType:
    try:
        import winreg
    except ImportError as error:
        raise RuntimeError("Windows PATH management is only available on Windows.") from error
    return winreg


@contextmanager
def _windows_path_mutex() -> Iterator[None]:
    if os.name != "nt":
        yield
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, "Local\\DebugOracleUserPath")
    if not handle:
        raise OSError(ctypes.get_last_error(), "Unable to create Windows PATH mutex")
    wait_result = kernel32.WaitForSingleObject(handle, 30_000)
    if wait_result not in {0, 0x80}:
        kernel32.CloseHandle(handle)
        raise RuntimeError("Timed out waiting to update the Windows user PATH")
    try:
        yield
    finally:
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)
