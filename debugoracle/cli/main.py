from __future__ import annotations

import argparse

from ..builder import DEFAULT_RTT_WINDOW
from ..session import DEFAULT_STALE_AFTER_SECONDS
from ..sources.streams.rtt import (
    DEFAULT_RTT_CONNECT_TIMEOUT,
    DEFAULT_RTT_HOST,
    DEFAULT_RTT_POLL_INTERVAL,
)
from .commands.evidence import cmd_fetch, cmd_report
from .commands.find_tcl_port import cmd_find_tcl_port
from .commands.init_workspace import (
    DEFAULT_MI_LOG_PATH,
    DEFAULT_RTT_LAUNCH_LOG_PATH,
    DEFAULT_RTT_LOG_PATH,
    DEFAULT_RTT_PORT as DEFAULT_INIT_RTT_PORT,
    DEFAULT_RTT_STATE_PATH,
    cmd_init_workspace,
)
from .commands.run_stop import (
    DEFAULT_RUN_PORT,
    cmd_run,
    cmd_stop,
)
from .commands.status_capture import cmd_capture_rtt, cmd_status


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_report_arguments(parser, args)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    cli_version = "0.1.0"

    parser = argparse.ArgumentParser(
        prog="dbgoracle",
        description=(
            "Passive embedded debug evidence packager for Cortex-Debug and GDB/MI sessions"
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=cli_version,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser(
        "status",
        help="Inspect session freshness and snapshot health",
        description=(
            "Inspect default artifacts in the workspace root or .dbgoracle folder "
            "without mutating the current debug session."
        ),
    )
    add_session_arguments(status)
    status.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    status.add_argument("--output", help="Optional output file path")
    status.set_defaults(func=cmd_status)

    capture = subparsers.add_parser(
        "capture-rtt",
        help="Capture RTT from an OpenOCD RTT TCP endpoint into a file",
        description=(
            "Connect to an OpenOCD RTT TCP endpoint, write the raw stream into a "
            "session log, and maintain a small transport state sidecar."
        ),
    )
    capture.add_argument(
        "--host",
        default=DEFAULT_RTT_HOST,
        help="RTT TCP host",
    )
    capture.add_argument(
        "--port",
        required=True,
        type=int,
        help="RTT TCP port exposed by OpenOCD",
    )
    capture.add_argument(
        "--output",
        required=True,
        help="Target RTT log file path",
    )
    capture.add_argument(
        "--state-out",
        help="Optional RTT capture state sidecar path",
    )
    capture.add_argument(
        "--connect-timeout",
        type=float,
        default=DEFAULT_RTT_CONNECT_TIMEOUT,
        help="Seconds to wait for the RTT TCP server before failing",
    )
    capture.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_RTT_POLL_INTERVAL,
        help="Socket poll interval in seconds while waiting for data",
    )
    capture.add_argument(
        "--idle-timeout",
        type=float,
        help="Optional idle timeout in seconds after connecting with no new bytes",
    )
    capture.add_argument(
        "--append",
        action="store_true",
        help="Append to the RTT output file instead of truncating it",
    )
    capture.set_defaults(func=cmd_capture_rtt)

    run = subparsers.add_parser(
        "run",
        help="Run RTT capture in foreground or as a managed detached session",
        description=(
            "Capture RTT from an OpenOCD RTT TCP endpoint. By default this runs in "
            "the foreground; use --detach for background automation."
        ),
    )
    run.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve default artifact paths",
    )
    run.add_argument(
        "--host",
        default=DEFAULT_RTT_HOST,
        help="RTT TCP host",
    )
    run.add_argument(
        "--port",
        type=int,
        default=DEFAULT_RUN_PORT,
        help="RTT TCP port exposed by OpenOCD",
    )
    run.add_argument(
        "--output",
        help="Target RTT log file path (defaults to <workspace>/.dbgoracle/session.rtt)",
    )
    run.add_argument(
        "--state-out",
        help="Optional RTT capture state sidecar path",
    )
    run.add_argument(
        "--connect-timeout",
        type=float,
        default=DEFAULT_RTT_CONNECT_TIMEOUT,
        help="Seconds to wait for RTT TCP server before failing",
    )
    run.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_RTT_POLL_INTERVAL,
        help="Socket poll interval in seconds while waiting for data",
    )
    run.add_argument(
        "--idle-timeout",
        type=float,
        help="Optional idle timeout in seconds after connecting with no new bytes",
    )
    run.add_argument(
        "--append",
        action="store_true",
        help="Append to RTT output instead of truncating on start",
    )
    run.add_argument(
        "--detach",
        action="store_true",
        help="Run capture in the background and return immediately",
    )
    run.set_defaults(func=cmd_run)

    stop = subparsers.add_parser(
        "stop",
        help="Stop the managed detached RTT capture for this workspace",
        description=(
            "Stop the detached RTT capture session started by `dbgoracle run --detach`."
        ),
    )
    stop.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve managed runtime metadata",
    )
    stop.add_argument(
        "--runtime-file",
        help="Optional override for detached run metadata path",
    )
    stop.add_argument(
        "--grace-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait after SIGTERM before force-kill fallback",
    )
    stop.set_defaults(func=cmd_stop)

    find_tcl_port = subparsers.add_parser(
        "find-tcl-port",
        help="Find the active OpenOCD Tcl port for the current workspace session",
        description=(
            "Inspect the live OpenOCD process, prefer the session that matches the "
            "workspace root, and optionally print a ready-to-run fetch command."
        ),
    )
    find_tcl_port.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to prefer the matching OpenOCD process and resolve the SVD file",
    )
    find_tcl_port.add_argument(
        "--pid",
        type=int,
        help="Optional specific OpenOCD PID to use when multiple sessions are active",
    )
    find_tcl_port.add_argument(
        "--print-fetch",
        action="store_true",
        help="Also print a dbgoracle fetch command when an SVD file can be resolved",
    )
    find_tcl_port.add_argument(
        "--json",
        action="store_true",
        help="Emit the discovered endpoint as JSON",
    )
    find_tcl_port.add_argument(
        "--connect-timeout",
        type=float,
        default=0.35,
        help="Seconds to wait when checking whether the Tcl endpoint is reachable",
    )
    find_tcl_port.set_defaults(func=cmd_find_tcl_port)

    fetch = subparsers.add_parser(
        "fetch",
        help="Resolve raw evidence inputs and build the latest reusable snapshot",
        description=(
            "Resolve explicit or auto-discovered raw evidence inputs, build a "
            "self-contained snapshot, and overwrite the default latest snapshot "
            "unless --state-out is provided."
        ),
    )
    add_input_arguments(fetch, include_snapshot_file=False)
    fetch.add_argument(
        "--state-out",
        default=None,
        help=(
            "Path for the reusable snapshot JSON written by fetch. When provided, this "
            "path is authoritative. When omitted, "
            "defaults to the latest_snapshot.json file beside the GDB/MI input, "
            "or falls back to <workspace>/latest_snapshot.json or "
            "<workspace>/.dbgoracle/latest_snapshot.json."
        ),
    )
    fetch.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain in the snapshot",
    )
    fetch.add_argument(
        "--svd-file",
        help="Optional CMSIS-SVD file used by fetch to capture safe-readable peripheral register values into the snapshot via the default OpenOCD backend",
    )
    fetch.add_argument(
        "--openocd-tcl-host",
        help="Optional OpenOCD Tcl host override used only for live peripheral capture with --svd-file",
    )
    fetch.add_argument(
        "--openocd-tcl-port",
        type=int,
        help="Optional OpenOCD Tcl port override used only for live peripheral capture with --svd-file",
    )
    fetch.set_defaults(func=cmd_fetch)

    report = subparsers.add_parser(
        "report",
        help="Render a human-readable evidence report or compact inspection JSON from a saved snapshot",
        description=(
            "Render a plain-text evidence summary by default, or compact JSON inspect "
            "sections with --vars, --gdb, --rtt, and --verbose. "
            "If omitted, --snapshot-file defaults to a discovered latest_snapshot.json."
        ),
    )
    add_snapshot_arguments(report)
    report.add_argument("--output", help="Optional output file path")
    report.add_argument(
        "--vars",
        nargs="*",
        help="Emit grouped variable evidence as compact JSON; optionally filter by exact case-insensitive variable names",
    )
    report.add_argument(
        "--gdb",
        action="store_true",
        help="Emit embedded GDB source data as compact JSON",
    )
    report.add_argument(
        "--rtt",
        action="store_true",
        help="Emit embedded RTT source data as compact JSON",
    )
    report.add_argument(
        "--verbose",
        action="store_true",
        help="Emit a compact JSON object combining summary, variables, streams, provenance, and embedded register data when present",
    )
    report.add_argument(
        "--regs-list",
        nargs="?",
        const="",
        metavar="PERIPHERAL",
        help="List captured peripherals, or list captured registers for one peripheral",
    )
    report.add_argument(
        "--regs",
        nargs="*",
        metavar="SELECTOR",
        help="Emit captured register data as compact JSON; selectors are PERIPHERAL or PERIPHERAL:REGISTER",
    )
    report.add_argument(
        "--tail",
        type=positive_int,
        help="Limit embedded stream sections to the last N events or lines",
    )
    report.add_argument(
        "--allow-unsafe",
        action="store_true",
        help="Render the full text report even when the trust verdict is unsafe",
    )
    report.set_defaults(func=cmd_report)

    init_workspace = subparsers.add_parser(
        "init-workspace",
        help="Create a DebugOracle workspace scaffold for a fresh project",
        description=(
            "Create the .dbgoracle and .vscode files needed for the supported "
            "Cortex-Debug/OpenOCD workspace flow."
        ),
    )
    init_workspace.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root where the scaffold should be created",
    )
    init_workspace.add_argument(
        "--executable",
        required=True,
        help="ELF or executable path stored in workspace settings",
    )
    init_workspace.add_argument(
        "--svd-file",
        help="Optional default SVD file path stored in workspace settings",
    )
    init_workspace.add_argument(
        "--attach",
        action="store_true",
        help="Emit DebugOracle attach fragments for an existing Cortex-Debug workspace instead of writing a fresh scaffold",
    )
    init_workspace.add_argument(
        "--openocd-config",
        action="append",
        help="Required OpenOCD config file stored in workspace settings; repeat for multiple files",
    )
    init_workspace.add_argument(
        "--mi-log-path",
        default=DEFAULT_MI_LOG_PATH,
        help="Workspace MI log path stored in settings.json",
    )
    init_workspace.add_argument(
        "--rtt-log-path",
        default=DEFAULT_RTT_LOG_PATH,
        help="Workspace RTT log path stored in settings.json",
    )
    init_workspace.add_argument(
        "--rtt-state-path",
        default=DEFAULT_RTT_STATE_PATH,
        help="Workspace RTT state sidecar path stored in settings.json",
    )
    init_workspace.add_argument(
        "--rtt-launch-log-path",
        default=DEFAULT_RTT_LAUNCH_LOG_PATH,
        help="Workspace RTT launch log path stored in settings.json",
    )
    init_workspace.add_argument(
        "--rtt-port",
        default=DEFAULT_INIT_RTT_PORT,
        help="Default RTT port stored in settings.json",
    )
    init_workspace.add_argument(
        "--with-rtt",
        action="store_true",
        help="Reserved flag for enabling RTT-specific guidance in the scaffold",
    )
    init_workspace.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing DebugOracle-managed scaffold files",
    )
    init_workspace.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    init_workspace.set_defaults(command="init_workspace", func=cmd_init_workspace)

    return parser


def positive_int(value: str) -> int:
    parsed = int(value, 10)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("tail must be a positive integer")
    return parsed


def validate_report_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if getattr(args, "command", None) != "report":
        return
    if getattr(args, "tail", None) is not None and not (
        getattr(args, "gdb", False) or getattr(args, "rtt", False) or getattr(args, "verbose", False)
    ):
        parser.error("--tail requires --gdb, --rtt, or --verbose")
    if getattr(args, "regs_list", None) is not None and getattr(args, "regs", None) is not None:
        parser.error("--regs-list and --regs cannot be used together")
    if getattr(args, "regs_list", None) not in (None, "") and ":" in getattr(args, "regs_list", ""):
        parser.error("--regs-list accepts an optional peripheral name only")
    for selector in getattr(args, "regs", None) or []:
        if not _is_valid_register_selector(selector):
            parser.error(f"invalid register selector: {selector}")




def add_session_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve default file paths",
    )
    parser.add_argument(
        "--snapshot-file",
        help="Override the snapshot JSON path (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--gdb-mi",
        help="Override the bounded GDB/MI transcript path (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--rtt",
        help="Override the RTT log path (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--rtt-state",
        help="Override the RTT capture state sidecar path (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--stale-after",
        type=int,
        default=DEFAULT_STALE_AFTER_SECONDS,
        help="Age in seconds after which artifacts are marked stale",
    )


def add_snapshot_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--snapshot-file",
        help="Existing snapshot JSON produced by fetch (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve default file paths",
    )


def add_input_arguments(
    parser: argparse.ArgumentParser,
    include_snapshot_file: bool,
) -> None:
    if include_snapshot_file:
        parser.add_argument(
            "--snapshot-file",
            help="Existing snapshot JSON produced by fetch (relative paths resolve from --workspace-root)",
        )
    parser.add_argument(
        "--gdb-mi",
        help="Path to a bounded GDB/MI transcript (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--rtt",
        help="Path to an RTT log captured alongside the MI transcript (relative paths resolve from --workspace-root)",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve default file paths",
    )

def _is_valid_register_selector(value: str) -> bool:
    if not value or value.count(":") > 1:
        return False
    if ":" not in value:
        return bool(value.strip())
    peripheral, register = value.split(":", 1)
    return bool(peripheral.strip()) and bool(register.strip())
