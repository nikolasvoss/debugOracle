from __future__ import annotations

import itertools
import os
import platform
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .docs_sidecar import discover_candidate_documents_bounded
from .jsonc import parse_jsonc
from .workspace_init_plan import AutomaticInitInventory

MAX_CONFIG_BYTES = 128 * 1024
MAX_DISCOVERY_FILES = 4096
MAX_DISCOVERY_CANDIDATES = 256
INPUT_DIRECTORY = "debugoracle-input"
EXCLUDED_DISCOVERY_DIRECTORIES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache"}
)


class ReadinessState(str, Enum):
    READY = "ready"
    NEEDS_HOST_DEPENDENCY = "needs_host_dependency"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    state: ReadinessState
    detail: str
    source: str
    requires_approval: bool = False


@dataclass(frozen=True)
class ReadinessReport:
    schema_version: str
    scope: str
    status: ReadinessState
    items: tuple[ReadinessItem, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "status": self.status.value,
            "items": [
                {
                    "key": item.key,
                    "status": item.state.value,
                    "detail": item.detail,
                    "source": item.source,
                    "requires_approval": item.requires_approval,
                }
                for item in self.items
            ],
        }


@dataclass(frozen=True)
class WorkspacePlan:
    workspace_root: str
    status: str
    candidates: dict[str, tuple[str, ...]]
    automatic_init_inventory: AutomaticInitInventory
    truncated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "scope": "workspace",
            "workspace_root": self.workspace_root,
            "status": self.status,
            "candidates": {
                key: list(values) for key, values in self.candidates.items()
            },
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class SessionPlan:
    workspace_root: str
    status: str
    checks: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "scope": "session",
            "workspace_root": self.workspace_root,
            "status": self.status,
            "target_contact": "not_attempted",
            "checks": self.checks,
        }


def collect_host_readiness(
    *, path: str | None = None, home: Path | None = None
) -> ReadinessReport:
    command_path = path if path is not None else None
    platform_name = platform.system()
    platform_state = (
        ReadinessState.READY if platform_name == "Linux" else ReadinessState.BLOCKED
    )
    items = (
        ReadinessItem(
            key="platform",
            state=platform_state,
            detail=f"Detected platform: {platform_name}",
            source="platform.system",
        ),
        ReadinessItem(
            key="python",
            state=(
                ReadinessState.READY
                if sys.version_info >= (3, 12)
                else ReadinessState.BLOCKED
            ),
            detail=("Python " + ".".join(str(part) for part in sys.version_info[:3])),
            source="sys.version_info",
        ),
        _command_item("pipx", "pipx", command_path),
        _command_item("openocd", "openocd", command_path),
        _command_item("arm_gdb", "arm-none-eabi-gdb", command_path),
        _command_item("vscode", "code", command_path),
        _cortex_debug_item(home or Path.home()),
    )
    status = _overall_status(items)
    return ReadinessReport(schema_version="1", scope="host", status=status, items=items)


def collect_workspace_plan(workspace_root: Path) -> WorkspacePlan:
    root = workspace_root.resolve(strict=True)
    candidates: dict[str, list[str]] = {
        "executables": [],
        "openocd_configs": [],
        "svd_files": [],
    }
    root_entries, truncated = _bounded_entries(root)
    for entry in root_entries:
        _collect_candidate_file(entry, root, candidates)
    if (
        len(candidates["executables"])
        + len(candidates["openocd_configs"])
        + len(candidates["svd_files"])
        >= MAX_DISCOVERY_CANDIDATES
    ):
        truncated = True
    scan_roots = tuple(
        root / name for name in (INPUT_DIRECTORY, "build", "out", "boards", "config")
    )
    for scan_root in scan_roots:
        if not scan_root.is_dir() or scan_root.is_symlink():
            continue
        entries, directory_truncated = _bounded_tree_entries(scan_root)
        truncated = truncated or directory_truncated
        for entry in entries:
            _collect_candidate_file(entry, root, candidates)
            if (
                sum(len(values) for values in candidates.values())
                >= MAX_DISCOVERY_CANDIDATES
            ):
                truncated = True
                break
        if truncated:
            break
    frozen_candidates = {
        key: tuple(sorted(set(values))) for key, values in candidates.items()
    }
    executable_count = len(frozen_candidates["executables"])
    status = (
        "blocked"
        if truncated
        else (
            "ready"
            if executable_count == 1
            else "needs_user_choice"
            if executable_count > 1
            else "blocked"
        )
    )
    automatic_init_inventory = _collect_automatic_init_inventory(
        root,
        frozen_candidates=frozen_candidates,
        legacy_truncated=truncated,
    )
    return WorkspacePlan(
        workspace_root=str(root),
        status=status,
        candidates=frozen_candidates,
        automatic_init_inventory=automatic_init_inventory,
        truncated=truncated,
    )


def collect_session_plan(workspace_root: Path) -> SessionPlan:
    root = workspace_root.resolve(strict=True)
    vscode_dir = root / ".vscode"
    checks = {
        "settings": _json_file_status(vscode_dir / "settings.json"),
        "launch": _json_file_status(vscode_dir / "launch.json"),
        "tasks": _json_file_status(vscode_dir / "tasks.json"),
        "mi_log_destination": _mi_log_status(root, vscode_dir / "settings.json"),
        "executable": _configured_path_status(
            root, vscode_dir / "settings.json", "debugoracle.executable"
        ),
        "openocd_configs": _launch_config_status(root, vscode_dir / "launch.json"),
        "mi_log_freshness": _mi_log_freshness(root, vscode_dir / "settings.json"),
        "rtt_port": _rtt_port_status(vscode_dir / "settings.json"),
    }
    blocking_states = {
        "missing",
        "invalid",
        "parent_missing",
        "unavailable",
        "stale",
        "listener_present",
        "outside_workspace",
        "too_large",
    }
    status = (
        "blocked"
        if any(value in blocking_states for value in checks.values())
        else "ready"
    )
    return SessionPlan(workspace_root=str(root), status=status, checks=checks)


def _command_item(key: str, command: str, path: str | None) -> ReadinessItem:
    resolved = shutil.which(command, path=path)
    if resolved:
        return ReadinessItem(
            key=key,
            state=ReadinessState.READY,
            detail=f"Found: {resolved}",
            source="PATH",
        )
    return ReadinessItem(
        key=key,
        state=ReadinessState.NEEDS_HOST_DEPENDENCY,
        detail=f"Not found on PATH: {command}",
        source="PATH",
    )


def _collect_candidate_file(
    path: Path, workspace_root: Path, candidates: dict[str, list[str]]
) -> None:
    if path.is_symlink() or not path.is_file():
        return
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(workspace_root):
        return
    suffix = resolved.suffix.lower()
    if suffix == ".elf":
        candidates["executables"].append(str(resolved))
    elif suffix == ".cfg":
        candidates["openocd_configs"].append(str(resolved))
    elif suffix == ".svd":
        candidates["svd_files"].append(str(resolved))


def _bounded_entries(directory: Path) -> tuple[tuple[Path, ...], bool]:
    with os.scandir(directory) as entries:
        selected = tuple(
            Path(entry.path)
            for entry in itertools.islice(entries, MAX_DISCOVERY_FILES + 1)
        )
    if len(selected) > MAX_DISCOVERY_FILES:
        return (), True
    return tuple(sorted(selected)), False


def _bounded_tree_entries(directory: Path) -> tuple[tuple[Path, ...], bool]:
    """Return a deterministic, symlink-free bounded file inventory."""

    pending = [directory]
    files: list[Path] = []
    seen = 0
    while pending:
        current = pending.pop()
        try:
            entries = tuple(sorted(Path(entry.path) for entry in os.scandir(current)))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > MAX_DISCOVERY_FILES:
                return (), True
            if entry.is_symlink():
                continue
            if entry.is_dir() and entry.name not in EXCLUDED_DISCOVERY_DIRECTORIES:
                pending.append(entry)
            elif entry.is_file():
                files.append(entry)
    return tuple(sorted(files)), False


def _collect_automatic_init_inventory(
    root: Path,
    *,
    frozen_candidates: dict[str, tuple[str, ...]],
    legacy_truncated: bool,
) -> AutomaticInitInventory:
    truncated_classes: set[str] = set()
    if legacy_truncated:
        truncated_classes.update(("executables", "raw_openocd_configs"))

    executable_candidates = _bounded_candidate_values(
        _trusted_candidate_values(root, frozen_candidates["executables"]),
        candidate_class="executables",
        truncated_classes=truncated_classes,
    )
    raw_openocd_configs = _bounded_candidate_values(
        _trusted_candidate_values(root, frozen_candidates["openocd_configs"]),
        candidate_class="raw_openocd_configs",
        truncated_classes=truncated_classes,
    )
    svd_candidates = _discover_direct_svd_candidates(
        root, truncated_classes=truncated_classes
    )
    documents = _discover_document_candidates(root, truncated_classes=truncated_classes)

    settings_path = root / ".vscode" / "settings.json"
    settings = (
        _read_jsonc_mapping(settings_path)
        if _is_trusted_workspace_file(settings_path, root)
        else None
    )
    configured_executable = _configured_workspace_file(
        root, settings, "debugoracle.executable"
    )
    configured_svd = _configured_workspace_file(root, settings, "debugoracle.svdFile")
    configured_openocd_configs = _configured_workspace_files(
        root, settings, "debugoracle.openocdConfigFiles"
    )
    cortex_debug_openocd_configs = _cortex_debug_openocd_configurations(root)

    return AutomaticInitInventory(
        workspace_root=str(root),
        executable_candidates=executable_candidates,
        svd_candidates=svd_candidates,
        raw_openocd_configs=raw_openocd_configs,
        configured_executable=configured_executable,
        configured_svd=configured_svd,
        configured_openocd_configs=configured_openocd_configs,
        cortex_debug_openocd_configs=cortex_debug_openocd_configs,
        documents=documents,
        truncated_candidate_classes=tuple(sorted(truncated_classes)),
    )


def _discover_direct_svd_candidates(
    root: Path, *, truncated_classes: set[str]
) -> tuple[str, ...]:
    values: list[str] = []
    for directory in (root / INPUT_DIRECTORY, root / ".dbgoracle"):
        if not directory.is_dir() or directory.is_symlink():
            continue
        entries, truncated = _bounded_tree_entries(directory)
        if truncated:
            truncated_classes.add("svd_files")
        values.extend(
            str(path.resolve(strict=True))
            for path in entries
            if path.suffix.lower() == ".svd" and _is_trusted_workspace_file(path, root)
        )
    return _bounded_candidate_values(
        tuple(values),
        candidate_class="svd_files",
        truncated_classes=truncated_classes,
    )


def _discover_document_candidates(
    root: Path, *, truncated_classes: set[str]
) -> tuple[str, ...]:
    discovered, truncated = discover_candidate_documents_bounded(
        root,
        max_entries=MAX_DISCOVERY_FILES,
        max_candidates=MAX_DISCOVERY_CANDIDATES,
    )
    if truncated:
        truncated_classes.add("documents")
    values = tuple(
        str(path.resolve(strict=True))
        for path in discovered
        if _is_trusted_workspace_file(path, root)
    )
    return _bounded_candidate_values(
        values,
        candidate_class="documents",
        truncated_classes=truncated_classes,
    )


def _bounded_candidate_values(
    values: tuple[str, ...],
    *,
    candidate_class: str,
    truncated_classes: set[str],
) -> tuple[str, ...]:
    canonical = tuple(sorted(set(values)))
    if len(canonical) > MAX_DISCOVERY_CANDIDATES:
        truncated_classes.add(candidate_class)
        return canonical[:MAX_DISCOVERY_CANDIDATES]
    return canonical


def _trusted_candidate_values(root: Path, values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        value for value in values if _is_trusted_workspace_file(Path(value), root)
    )


def _configured_workspace_file(
    root: Path, payload: dict[str, object] | None, key: str
) -> str | None:
    value = payload.get(key) if payload is not None else None
    if not isinstance(value, str) or not value.strip():
        return None
    path = _unresolved_workspace_path(value, root)
    if path is None or not _is_trusted_workspace_file(path, root):
        return None
    return str(path.resolve(strict=True))


def _configured_workspace_files(
    root: Path, payload: dict[str, object] | None, key: str
) -> tuple[str, ...]:
    values = payload.get(key) if payload is not None else None
    if not isinstance(values, list) or not values:
        return ()
    resolved: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            return ()
        path = _unresolved_workspace_path(value, root)
        if path is None or not _is_trusted_workspace_file(path, root):
            return ()
        resolved.append(str(path.resolve(strict=True)))
    return tuple(resolved)


def _cortex_debug_openocd_configurations(root: Path) -> tuple[tuple[str, ...], ...]:
    launch_path = root / ".vscode" / "launch.json"
    if not _is_trusted_workspace_file(launch_path, root):
        return ()
    payload = _read_jsonc_mapping(launch_path)
    configurations = payload.get("configurations") if payload is not None else None
    if not isinstance(configurations, list):
        return ()
    selected: list[tuple[str, ...]] = []
    for configuration in configurations:
        if not isinstance(configuration, dict):
            continue
        if configuration.get("type") != "cortex-debug":
            continue
        values = configuration.get("configFiles")
        if not isinstance(values, list) or not values:
            continue
        normalized = _normalize_workspace_file_list(root, values)
        if normalized:
            selected.append(normalized)
    return tuple(sorted(selected))


def _normalize_workspace_file_list(root: Path, values: list[object]) -> tuple[str, ...]:
    resolved: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            return ()
        path = _unresolved_workspace_path(value, root)
        if path is None or not _is_trusted_workspace_file(path, root):
            return ()
        resolved.append(str(path.resolve(strict=True)))
    return tuple(resolved)


def _is_trusted_workspace_file(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError:
        return False
    readable_mode = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    return (
        resolved.is_relative_to(root)
        and stat.S_ISREG(metadata.st_mode)
        and bool(metadata.st_mode & readable_mode)
    )


def _unresolved_workspace_path(value: str, root: Path) -> Path:
    replaced = value.replace("${workspaceFolder}", str(root))
    path = Path(replaced)
    return path if path.is_absolute() else root / path


def _cortex_debug_item(home: Path) -> ReadinessItem:
    extension_dirs = (
        home / ".vscode" / "extensions",
        home / ".vscode-server" / "extensions",
        home
        / ".var"
        / "app"
        / "com.visualstudio.code"
        / "data"
        / "vscode"
        / "extensions",
    )
    for extension_dir in extension_dirs:
        if any(extension_dir.glob("marus25.cortex-debug-*")):
            return ReadinessItem(
                key="cortex_debug",
                state=ReadinessState.READY,
                detail="Found Cortex-Debug extension",
                source=str(extension_dir),
            )
    return ReadinessItem(
        key="cortex_debug",
        state=ReadinessState.NEEDS_HOST_DEPENDENCY,
        detail="Cortex-Debug extension was not found in supported local extension folders.",
        source="VS Code extension folders",
    )


def _overall_status(items: tuple[ReadinessItem, ...]) -> ReadinessState:
    if any(item.state is ReadinessState.BLOCKED for item in items):
        return ReadinessState.BLOCKED
    if any(item.state is ReadinessState.NEEDS_HOST_DEPENDENCY for item in items):
        return ReadinessState.NEEDS_HOST_DEPENDENCY
    return ReadinessState.READY


def _json_file_status(path: Path) -> str:
    if not path.is_file():
        return "missing"
    if path.stat().st_size > MAX_CONFIG_BYTES:
        return "too_large"
    try:
        payload = parse_jsonc(path.read_text(encoding="utf-8"))
    except OSError:
        return "invalid"
    return "ready" if isinstance(payload, dict) else "invalid"


def _mi_log_status(workspace_root: Path, settings_path: Path) -> str:
    if _json_file_status(settings_path) != "ready":
        return "unavailable"
    try:
        payload = parse_jsonc(settings_path.read_text(encoding="utf-8"))
    except OSError:
        return "unavailable"
    if not isinstance(payload, dict):
        return "invalid"
    value = payload.get("debugoracle.miLogPath")
    if not isinstance(value, str) or not value.strip():
        return "missing"
    resolved = _workspace_path(value, workspace_root)
    if resolved is None:
        return "outside_workspace"
    return "ready" if resolved.parent.is_dir() else "parent_missing"


def _configured_path_status(workspace_root: Path, settings_path: Path, key: str) -> str:
    payload = _read_jsonc_mapping(settings_path)
    value = payload.get(key) if payload is not None else None
    if not isinstance(value, str) or not value.strip():
        return "missing"
    resolved = _workspace_path(value, workspace_root)
    if resolved is None:
        return "outside_workspace"
    return "ready" if resolved.is_file() else "missing"


def _launch_config_status(workspace_root: Path, launch_path: Path) -> str:
    payload = _read_jsonc_mapping(launch_path)
    configurations = payload.get("configurations") if payload is not None else None
    if not isinstance(configurations, list):
        return "missing"
    for configuration in configurations:
        if (
            not isinstance(configuration, dict)
            or configuration.get("type") != "cortex-debug"
        ):
            continue
        config_files = configuration.get("configFiles")
        if not isinstance(config_files, list) or not config_files:
            return "missing"
        paths = [
            _workspace_path(value, workspace_root)
            for value in config_files
            if isinstance(value, str)
        ]
        if any(path is None for path in paths):
            return "outside_workspace"
        contained_paths = tuple(path for path in paths if path is not None)
        return (
            "ready"
            if contained_paths and all(path.is_file() for path in contained_paths)
            else "missing"
        )
    return "missing"


def _read_jsonc_mapping(path: Path) -> dict[str, object] | None:
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            return None
    except OSError:
        return None
    try:
        payload = parse_jsonc(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _workspace_path(value: str, workspace_root: Path) -> Path | None:
    replaced = value.replace("${workspaceFolder}", str(workspace_root))
    path = Path(replaced)
    candidate = path if path.is_absolute() else workspace_root / path
    resolved = candidate.resolve(strict=False)
    return resolved if resolved.is_relative_to(workspace_root) else None


def _mi_log_freshness(workspace_root: Path, settings_path: Path) -> str:
    payload = _read_jsonc_mapping(settings_path)
    value = payload.get("debugoracle.miLogPath") if payload is not None else None
    if not isinstance(value, str) or not value.strip():
        return "unavailable"
    path = _workspace_path(value, workspace_root)
    if path is None:
        return "outside_workspace"
    if not path.is_file():
        return "not_started"
    return "fresh" if time.time() - path.stat().st_mtime <= 300 else "stale"


def _rtt_port_status(settings_path: Path) -> str:
    payload = _read_jsonc_mapping(settings_path)
    value = payload.get("debugoracle.rttPort") if payload is not None else None
    if not isinstance(value, str) or not value.isdecimal():
        return "not_configured"
    port = int(value, 10)
    return "listener_present" if _has_local_tcp_listener(port) else "available"


def _has_local_tcp_listener(port: int) -> bool:
    try:
        lines = (Path("/proc/net/tcp").read_text(encoding="utf-8")).splitlines()[1:]
    except OSError:
        return False
    for line in lines:
        fields = line.split()
        if len(fields) >= 4 and fields[3] == "0A":
            _address, port_hex = fields[1].split(":", maxsplit=1)
            if int(port_hex, 16) == port:
                return True
    return False
