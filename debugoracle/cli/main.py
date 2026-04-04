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
from .commands.guard_openocd_launch import cmd_guard_openocd_launch
from .commands.install_cli import cmd_install_cli
from .commands.uninstall_cli import cmd_uninstall_cli
from .commands.docs_cli import (
    cmd_docs_doctor,
    cmd_docs_ingest,
    cmd_docs_search,
    cmd_docs_status,
)
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

    guard_openocd_launch = subparsers.add_parser(
        "guard-openocd-launch",
        help="Fail early when a workspace-matching OpenOCD session is already active",
        description=(
            "Check whether an OpenOCD process already owns this workspace so generated "
            "attach launches can fail early instead of competing with `make debug`."
        ),
    )
    guard_openocd_launch.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to detect matching OpenOCD processes",
    )
    guard_openocd_launch.set_defaults(func=cmd_guard_openocd_launch)

    _add_docs_parser(subparsers)
    _add_fetch_parser(subparsers)
    _add_report_parser(subparsers)
    _add_install_cli_parser(subparsers)
    _add_uninstall_cli_parser(subparsers)
    _add_init_workspace_parser(subparsers)

    return parser


def _add_docs_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    docs = subparsers.add_parser(
        "docs",
        help="Manage locally ingested reference manuals and datasheets",
        description=(
            "Ingest local manuals or datasheets into nearby sidecar artifacts, then "
            "search or inspect their local status with explicit quality signals."
        ),
    )
    docs_subparsers = docs.add_subparsers(dest="docs_command", required=True)

    docs_ingest = docs_subparsers.add_parser(
        "ingest",
        help="Ingest explicit manuals or discovered PDFs into local sidecar artifacts",
    )
    docs_ingest.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used for relative paths and discovery under doc/ or docs/",
    )
    docs_ingest.add_argument(
        "--file",
        action="append",
        help="Explicit document file to ingest; repeat for multiple files",
    )
    docs_ingest.add_argument(
        "--folder",
        action="append",
        help="Explicit folder of manuals to ingest; repeat for multiple folders",
    )
    docs_ingest.add_argument(
        "--yes",
        action="store_true",
        help="Confirm ingestion of discovered PDFs when no explicit inputs are given",
    )
    docs_ingest.add_argument(
        "--parser",
        choices=["pymupdf", "docling"],
        default="pymupdf",
        help="Parser backend for PDF ingestion",
    )
    docs_ingest.add_argument(
        "--semantic",
        action="store_true",
        help="Build semantic embeddings for hybrid search (requires optional dependency)",
    )
    docs_ingest.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingest even when source hash is unchanged",
    )
    docs_ingest.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable TTY prompts and run docs ingest in non-interactive mode",
    )
    docs_ingest.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    docs_ingest.add_argument("--output", help="Optional output file path")
    docs_ingest.set_defaults(command="docs", func=cmd_docs_ingest)

    docs_search = docs_subparsers.add_parser(
        "search",
        help="Search the local docs sidecar index with exact-term-friendly ranking",
    )
    docs_search.add_argument("query", help="Search query")
    docs_search.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to discover sidecar artifacts",
    )
    docs_search.add_argument(
        "--file",
        action="append",
        help="Optional explicit ingested source document to restrict search scope",
    )
    docs_search.add_argument(
        "--limit",
        type=positive_int,
        default=5,
        help="Maximum number of search results to return",
    )
    docs_search.add_argument(
        "--semantic",
        action="store_true",
        help="Enable hybrid BM25 + semantic search when embeddings are available",
    )
    docs_search.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    docs_search.add_argument("--output", help="Optional output file path")
    docs_search.set_defaults(command="docs", func=cmd_docs_search)

    docs_status = docs_subparsers.add_parser(
        "status",
        help="Inspect the ingest health of local docs sidecar artifacts",
    )
    docs_status.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to discover sidecar artifacts",
    )
    docs_status.add_argument(
        "--file",
        action="append",
        help="Optional explicit source document whose sidecar status should be inspected",
    )
    docs_status.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    docs_status.add_argument("--output", help="Optional output file path")
    docs_status.set_defaults(command="docs", func=cmd_docs_status)

    docs_doctor = docs_subparsers.add_parser(
        "doctor",
        help="Check docs ingest dependencies and suggest exact remediation commands",
    )
    docs_doctor.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    docs_doctor.add_argument("--output", help="Optional output file path")
    docs_doctor.set_defaults(command="docs", func=cmd_docs_doctor)


def _add_fetch_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
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


def _add_report_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
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


def _add_install_cli_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    install_cli = subparsers.add_parser(
        "install-cli",
        help=argparse.SUPPRESS,
        description="Internal installer entrypoint used by the Linux launcher.",
    )
    install_cli.add_argument(
        "--manifest-url",
        help="Installer manifest URL",
    )
    install_cli.add_argument(
        "--channel",
        default="stable",
        help="Release channel to request from the installer manifest",
    )
    install_cli.add_argument(
        "--package-source",
        help="Optional package source override passed to pipx",
    )
    install_cli.add_argument(
        "--yes",
        action="store_true",
        help="Accept optional PATH profile updates without prompting",
    )
    install_cli.add_argument(
        "--no-doctor",
        action="store_true",
        help="Skip optional post-install environment guidance",
    )
    install_cli.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    install_cli.set_defaults(command="install_cli", func=cmd_install_cli)


def _add_init_workspace_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
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


def _add_uninstall_cli_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    uninstall_cli = subparsers.add_parser(
        "uninstall-cli",
        help=argparse.SUPPRESS,
        description="Internal uninstall entrypoint used by the Linux launcher.",
    )
    uninstall_cli.add_argument(
        "--manifest-url",
        help=argparse.SUPPRESS,
    )
    uninstall_cli.add_argument(
        "--keep-path",
        action="store_true",
        help="Skip PATH profile cleanup",
    )
    uninstall_cli.add_argument(
        "--force-legacy-path-cleanup",
        action="store_true",
        help="Remove matching legacy PATH lines even when they are not installer-marked",
    )
    uninstall_cli.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    uninstall_cli.set_defaults(command="uninstall_cli", func=cmd_uninstall_cli)


def positive_int(value: str) -> int:
    parsed = int(value, 10)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("tail must be a positive integer")
    return parsed


def validate_report_arguments(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if getattr(args, "command", None) != "report":
        return
    if getattr(args, "tail", None) is not None and not (
        getattr(args, "gdb", False)
        or getattr(args, "rtt", False)
        or getattr(args, "verbose", False)
    ):
        parser.error("--tail requires --gdb, --rtt, or --verbose")
    if (
        getattr(args, "regs_list", None) is not None
        and getattr(args, "regs", None) is not None
    ):
        parser.error("--regs-list and --regs cannot be used together")
    if getattr(args, "regs_list", None) not in (None, "") and ":" in getattr(
        args, "regs_list", ""
    ):
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
