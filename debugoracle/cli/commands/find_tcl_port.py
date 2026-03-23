from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

from ...openocd import (
    DEFAULT_OPENOCD_HOST,
    DISCOVERY_MATCHED,
    DISCOVERY_MULTIPLE,
    DISCOVERY_NO_SESSION,
    DISCOVERY_PID_NOT_FOUND,
    DISCOVERY_UNREACHABLE,
    OpenOcdCandidate,
    OpenOcdDiscoveryResult,
    _discover_openocd_candidates_from_proc,
    _discover_openocd_candidates_from_ps,
    _parse_ps_output,
    discover_openocd_candidates,
    is_tcp_endpoint_reachable,
    parse_openocd_ports,
    select_openocd_candidate,
)
from .evidence import resolve_fetch_svd_file


def cmd_find_tcl_port(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    result = _discover_workspace_session_for_cli(
        workspace_root,
        requested_pid=args.pid,
        connect_timeout=args.connect_timeout,
    )
    candidate = result.candidate
    if candidate is None:
        print(_candidate_error_message(result), file=sys.stderr)
        return 2

    reachable = result.status == DISCOVERY_MATCHED
    svd_file, svd_notice = resolve_svd_file(workspace_root)

    if args.json:
        payload = {
            "pid": candidate.pid,
            "cwd": candidate.cwd,
            "host": candidate.host,
            "tcl_port": candidate.tcl_port,
            "gdb_port": candidate.gdb_port,
            "telnet_port": candidate.telnet_port,
            "reachable": reachable,
            "svd_file": svd_file,
            "svd_notice": svd_notice,
            "fetch_command": build_fetch_command(workspace_root, candidate.host, candidate.tcl_port, svd_file)
            if args.print_fetch
            else None,
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"OpenOCD Tcl port: {candidate.tcl_port}")
    print(f"PID: {candidate.pid}")
    if candidate.cwd:
        print(f"CWD: {candidate.cwd}")
    if candidate.gdb_port is not None:
        print(f"GDB port: {candidate.gdb_port}")
    if candidate.telnet_port is not None:
        print(f"Telnet port: {candidate.telnet_port}")
    print(f"Reachable: {'yes' if reachable else 'no'}")
    if svd_file:
        print(f"Resolved SVD: {svd_file}")
    elif args.print_fetch:
        print("Resolved SVD: none")

    if svd_notice:
        print(svd_notice, file=sys.stderr)
    if result.status == DISCOVERY_UNREACHABLE:
        print(
            "The matching OpenOCD session was found, but its Tcl endpoint is not reachable yet. "
            "Keep the debug session running and verify the reported port before retrying.",
            file=sys.stderr,
        )

    if args.print_fetch:
        command = build_fetch_command(workspace_root, candidate.host, candidate.tcl_port, svd_file)
        if command is None:
            print(
                "Fetch command: not available because no SVD file was resolved. "
                "Pass --svd-file yourself or store debugoracle.svdFile in .vscode/settings.json.",
                file=sys.stderr,
            )
            return 0
        print("")
        print("Run this:")
        print(command)
    return 0


def _candidate_error_message(result: OpenOcdDiscoveryResult) -> str:
    if result.status == DISCOVERY_PID_NOT_FOUND and result.requested_pid is not None:
        return f"No active OpenOCD session matched pid {result.requested_pid}."
    if result.status == DISCOVERY_MULTIPLE:
        pids = ", ".join(str(candidate.pid) for candidate in sorted(result.candidates, key=lambda item: item.pid))
        return (
            "Multiple active OpenOCD sessions match this workspace selection while a debug session is running. "
            f"Re-run `dbgoracle find-tcl-port --pid <PID>` with one of: {pids}."
        )
    return (
        "No active OpenOCD process with an explicit Tcl port was found. "
        "A debug session must already be running before `dbgoracle find-tcl-port` can help. "
        "Start the debug session first, then rerun `dbgoracle find-tcl-port`."
    )


def _discover_workspace_session_for_cli(
    workspace_root: Path,
    *,
    requested_pid: int | None,
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


def select_candidate(
    candidates: list[OpenOcdCandidate],
    *,
    workspace_root: Path,
    requested_pid: int | None,
) -> OpenOcdCandidate | None:
    return select_openocd_candidate(
        candidates,
        workspace_root=workspace_root,
        requested_pid=requested_pid,
    )


def parse_ps_output(raw_text: str):
    return _parse_ps_output(raw_text)


def resolve_svd_file(workspace_root: Path) -> tuple[str | None, str | None]:
    resolved, _, notice = resolve_fetch_svd_file(SimpleNamespace(svd_file=None), workspace_root)
    return resolved, notice


def build_fetch_command(
    workspace_root: Path,
    host: str,
    tcl_port: int,
    svd_file: str | None,
) -> str | None:
    if not svd_file:
        return None
    parts = [
        "dbgoracle",
        "fetch",
        "--workspace-root",
        str(workspace_root),
        "--svd-file",
        svd_file,
    ]
    if host != DEFAULT_OPENOCD_HOST:
        parts.extend(["--openocd-tcl-host", host])
    parts.extend(["--openocd-tcl-port", str(tcl_port)])
    return " ".join(_shell_quote(part) for part in parts)


def _shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=+-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"
