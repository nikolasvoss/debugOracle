from __future__ import annotations

import itertools
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .jsonc import parse_jsonc

MAX_CONFIG_BYTES = 128 * 1024
MAX_DISCOVERY_FILES = 4096
MAX_DISCOVERY_CANDIDATES = 256


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
                if sys.version_info >= (3, 10)
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
    scan_roots = tuple(root / name for name in ("build", "out", "boards", "config"))
    for scan_root in scan_roots:
        if not scan_root.is_dir() or scan_root.is_symlink():
            continue
        entries, directory_truncated = _bounded_entries(scan_root)
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
    frozen_candidates = {key: tuple(values) for key, values in candidates.items()}
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
    return WorkspacePlan(
        workspace_root=str(root),
        status=status,
        candidates=frozen_candidates,
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
            itertools.islice(
                (Path(entry.path) for entry in entries), MAX_DISCOVERY_FILES + 1
            )
        )
    return (
        tuple(sorted(selected[:MAX_DISCOVERY_FILES])),
        len(selected) > MAX_DISCOVERY_FILES,
    )


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
    except OSError:
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
