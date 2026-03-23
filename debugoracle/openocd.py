from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
from typing import Iterable

DEFAULT_OPENOCD_HOST = "127.0.0.1"
OPENOCD_PROCESS_NAME = "openocd"

DISCOVERY_MATCHED = "matched"
DISCOVERY_UNREACHABLE = "unreachable"
DISCOVERY_NO_SESSION = "no_session"
DISCOVERY_MULTIPLE = "multiple_matches"
DISCOVERY_PID_NOT_FOUND = "pid_not_found"


@dataclass(frozen=True)
class OpenOcdCandidate:
    pid: int
    argv: tuple[str, ...]
    cwd: str | None
    host: str
    tcl_port: int
    gdb_port: int | None
    telnet_port: int | None

    @property
    def command(self) -> str:
        return " ".join(self.argv)


@dataclass(frozen=True)
class OpenOcdDiscoveryResult:
    status: str
    candidate: OpenOcdCandidate | None = None
    candidates: tuple[OpenOcdCandidate, ...] = ()
    requested_pid: int | None = None


@dataclass
class OpenOcdReachabilityError(Exception):
    host: str
    port: int
    detail: str

    def __str__(self) -> str:
        return f"Could not reach the OpenOCD live-read backend at {self.host}:{self.port}: {self.detail}"


def discover_workspace_openocd_session(
    workspace_root: Path,
    *,
    requested_pid: int | None = None,
    connect_timeout: float,
) -> OpenOcdDiscoveryResult:
    candidates = tuple(discover_openocd_candidates())
    candidate = select_openocd_candidate(
        list(candidates),
        workspace_root=workspace_root,
        requested_pid=requested_pid,
    )
    if candidate is None:
        if requested_pid is not None:
            return OpenOcdDiscoveryResult(
                status=DISCOVERY_PID_NOT_FOUND,
                candidates=candidates,
                requested_pid=requested_pid,
            )
        if not candidates:
            return OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION)
        return OpenOcdDiscoveryResult(status=DISCOVERY_MULTIPLE, candidates=candidates)
    if not is_tcp_endpoint_reachable(candidate.host, candidate.tcl_port, timeout_seconds=connect_timeout):
        return OpenOcdDiscoveryResult(
            status=DISCOVERY_UNREACHABLE,
            candidate=candidate,
            candidates=candidates,
            requested_pid=requested_pid,
        )
    return OpenOcdDiscoveryResult(
        status=DISCOVERY_MATCHED,
        candidate=candidate,
        candidates=candidates,
        requested_pid=requested_pid,
    )


def discover_openocd_candidates() -> Iterable[OpenOcdCandidate]:
    linux_candidates = list(_discover_openocd_candidates_from_proc())
    if linux_candidates:
        return linux_candidates
    return list(_discover_openocd_candidates_from_ps())


def select_openocd_candidate(
    candidates: list[OpenOcdCandidate],
    *,
    workspace_root: Path,
    requested_pid: int | None,
) -> OpenOcdCandidate | None:
    if requested_pid is not None:
        for candidate in candidates:
            if candidate.pid == requested_pid:
                return candidate
        return None
    if not candidates:
        return None
    workspace_text = str(workspace_root)
    cwd_matches = [candidate for candidate in candidates if candidate.cwd and Path(candidate.cwd).resolve() == workspace_root]
    if len(cwd_matches) == 1:
        return cwd_matches[0]
    if len(cwd_matches) > 1:
        return None
    path_matches = [candidate for candidate in candidates if workspace_text in candidate.command]
    if len(path_matches) == 1:
        return path_matches[0]
    if len(path_matches) > 1:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


def is_tcp_endpoint_reachable(host: str, port: int, *, timeout_seconds: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def parse_openocd_ports(argv: tuple[str, ...]) -> dict[str, int | None]:
    ports: dict[str, int | None] = {
        "gdb_port": None,
        "tcl_port": None,
        "telnet_port": None,
    }
    commands = _extract_openocd_command_strings(argv)
    for command in commands:
        for key in tuple(ports):
            match = re.search(rf"\b{re.escape(key)}\s+(\d+)\b", command)
            if match:
                ports[key] = int(match.group(1), 10)
    return ports


def looks_like_openocd_argv(argv: tuple[str, ...]) -> bool:
    if not argv:
        return False
    executable = Path(argv[0]).name.lower()
    if executable == OPENOCD_PROCESS_NAME:
        return True
    return any(Path(part).name.lower() == OPENOCD_PROCESS_NAME for part in argv)


def _discover_openocd_candidates_from_proc() -> Iterable[OpenOcdCandidate]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    candidates: list[OpenOcdCandidate] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = _read_proc_cmdline(entry / "cmdline")
        except OSError:
            continue
        if not argv or not looks_like_openocd_argv(argv):
            continue
        ports = parse_openocd_ports(argv)
        if ports["tcl_port"] is None:
            continue
        try:
            cwd = os.readlink(entry / "cwd")
        except OSError:
            cwd = None
        candidates.append(
            OpenOcdCandidate(
                pid=int(entry.name, 10),
                argv=argv,
                cwd=cwd,
                host=DEFAULT_OPENOCD_HOST,
                tcl_port=ports["tcl_port"],
                gdb_port=ports["gdb_port"],
                telnet_port=ports["telnet_port"],
            )
        )
    return candidates


def _discover_openocd_candidates_from_ps() -> Iterable[OpenOcdCandidate]:
    commands = (
        ["ps", "-eo", "pid=,args="],
        ["ps", "-ax", "-o", "pid=", "-o", "command="],
    )
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        candidates = list(_parse_ps_output(completed.stdout))
        if candidates:
            return candidates
    return []


def _parse_ps_output(raw_text: str) -> Iterable[OpenOcdCandidate]:
    candidates: list[OpenOcdCandidate] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if not pid_text.isdigit() or not command:
            continue
        if OPENOCD_PROCESS_NAME not in command:
            continue
        try:
            argv = tuple(shlex.split(command))
        except ValueError:
            continue
        if not looks_like_openocd_argv(argv):
            continue
        ports = parse_openocd_ports(argv)
        if ports["tcl_port"] is None:
            continue
        candidates.append(
            OpenOcdCandidate(
                pid=int(pid_text, 10),
                argv=argv,
                cwd=None,
                host=DEFAULT_OPENOCD_HOST,
                tcl_port=ports["tcl_port"],
                gdb_port=ports["gdb_port"],
                telnet_port=ports["telnet_port"],
            )
        )
    return candidates


def _read_proc_cmdline(path: Path) -> tuple[str, ...]:
    raw = path.read_bytes()
    parts = [chunk.decode("utf-8", errors="replace") for chunk in raw.split(b"\x00") if chunk]
    return tuple(parts)


def _extract_openocd_command_strings(argv: tuple[str, ...]) -> list[str]:
    commands: list[str] = []
    for index, arg in enumerate(argv):
        if arg == "-c" and index + 1 < len(argv):
            commands.append(argv[index + 1])
            continue
        if arg.startswith("-c") and len(arg) > 2:
            commands.append(arg[2:])
    commands.extend(argv)
    return commands
