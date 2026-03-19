from __future__ import annotations

import argparse

from ..builder import DEFAULT_RTT_WINDOW
from ..session import DEFAULT_STALE_AFTER_SECONDS
from ..sources.streams.rtt import (
    DEFAULT_RTT_CONNECT_TIMEOUT,
    DEFAULT_RTT_HOST,
    DEFAULT_RTT_POLL_INTERVAL,
)
from .commands.evidence import cmd_observe, cmd_prompt, cmd_report, cmd_snapshot
from .commands.run_stop import (
    DEFAULT_RUN_PORT,
    cmd_run,
    cmd_stop,
)
from .commands.status_capture import cmd_capture_rtt, cmd_status


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    cli_version = "0.1.0"

    parser = argparse.ArgumentParser(
        prog="dbgoracle",
        description=(
            "Passive embedded debug evidence packager for Cortex-Debug and GDB/MI sessions"
        ),
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

    observe = subparsers.add_parser(
        "observe",
        help="Capture and store a reusable snapshot for later report or prompt use",
        description=(
            "Build and store a reusable evidence snapshot from a bounded GDB/MI "
            "transcript plus optional RTT logs."
        ),
    )
    add_input_arguments(observe, include_snapshot_file=False)
    observe.add_argument(
        "--state-out",
        default=None,
        help=(
            "Path for the reusable snapshot JSON written by observe. When provided, this "
            "path is authoritative. When omitted, "
            "defaults to the latest_snapshot.json file beside the GDB/MI input, "
            "or falls back to <workspace>/latest_snapshot.json or "
            "<workspace>/.dbgoracle/latest_snapshot.json."
        ),
    )
    observe.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain in the snapshot",
    )
    observe.set_defaults(func=cmd_observe)

    snapshot = subparsers.add_parser(
        "snapshot",
        help="Advanced snapshot rendering for automation or low-level inspection",
        description=(
            "Render a snapshot from a saved bundle or bounded raw inputs. Most users "
            "should start with observe, then use report or prompt."
        ),
    )
    add_input_arguments(snapshot, include_snapshot_file=True)
    snapshot.add_argument(
        "--format",
        choices=["json", "text", "markdown"],
        default="json",
        help="Output format",
    )
    snapshot.add_argument(
        "--output",
        help="Optional output file path",
    )
    snapshot.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain when building from raw inputs",
    )
    add_variable_selector_arguments(snapshot)
    snapshot.set_defaults(func=cmd_snapshot)

    prompt = subparsers.add_parser(
        "prompt",
        help="Build a ChatGPT-ready prompt package from a snapshot or raw inputs",
        description=(
            "Package a saved snapshot or bounded raw inputs into a prompt you can "
            "paste into ChatGPT."
        ),
    )
    add_input_arguments(prompt, include_snapshot_file=True)
    prompt.add_argument("--goal", required=True, help="Investigation goal to hand to ChatGPT")
    prompt.add_argument("--intent", help="Optional intended system state text")
    prompt.add_argument("--intent-file", help="Optional file containing intended system state text")
    prompt.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="markdown",
        help="Prompt output format",
    )
    prompt.add_argument("--full", action="store_true", help="Expand the evidence appendix")
    prompt.add_argument("--output", help="Optional output file path")
    prompt.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain when building from raw inputs",
    )
    add_variable_selector_arguments(prompt)
    prompt.set_defaults(func=cmd_prompt)

    report = subparsers.add_parser(
        "report",
        help="Render a human-readable evidence report from a snapshot or raw inputs",
        description=(
            "Render a human-readable evidence report from a saved snapshot or bounded "
            "raw inputs."
        ),
    )
    add_input_arguments(report, include_snapshot_file=True)
    report.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="markdown",
        help="Report output format",
    )
    report.add_argument("--output", help="Optional output file path")
    report.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain when building from raw inputs",
    )
    add_variable_selector_arguments(report)
    report.set_defaults(func=cmd_report)

    return parser


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


def add_input_arguments(
    parser: argparse.ArgumentParser,
    include_snapshot_file: bool,
) -> None:
    if include_snapshot_file:
        parser.add_argument(
            "--snapshot-file",
            help="Existing snapshot JSON produced by observe (relative paths resolve from --workspace-root)",
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
        "--export-raw",
        action="store_true",
        help=(
            "Export raw MI/RTT inputs to sidecar files. Raw export also happens "
            "automatically when parse warnings are detected."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve default file paths",
    )


def add_variable_selector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--var-scope",
        choices=["local", "watchpoint", "unknown", "all"],
        default="all",
        help="Variable evidence scope to render",
    )
    parser.add_argument(
        "--var-name",
        action="append",
        default=[],
        help="Optional variable/watchpoint name filter; repeat to request multiple names",
    )
    parser.add_argument(
        "--var-detail",
        choices=["compact", "full"],
        default="compact",
        help="Variable evidence detail level",
    )
