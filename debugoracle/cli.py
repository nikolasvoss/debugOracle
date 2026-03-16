from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .builder import (
    DEFAULT_RTT_WINDOW,
    FULL_RTT_WINDOW,
    build_bundle_from_stream,
    build_bundle_from_files,
    load_bundle,
    save_bundle,
)
from .live import (
    DEFAULT_LIVE_BACKEND,
    available_backends,
    build_live_backend,
    render_live_status,
    render_memory_result,
    render_register_result,
    validate_memory_request,
)
from .models import InvestigationRequest
from .output import render_prompt, render_report, render_snapshot
from .rtt import (
    DEFAULT_RTT_CONNECT_TIMEOUT,
    DEFAULT_RTT_HOST,
    DEFAULT_RTT_POLL_INTERVAL,
    RttCaptureTimeoutError,
    capture_rtt,
    default_state_path,
)
from .session import (
    DEFAULT_SESSION_DIR,
    DEFAULT_SNAPSHOT_FILENAME,
    DEFAULT_STALE_AFTER_SECONDS,
    SessionConfig,
    collect_session_status,
    render_session_status,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbgoracle",
        description=(
            "Passive embedded debug evidence packager for Cortex-Debug and GDB/MI sessions"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser(
        "status",
        help="Inspect session freshness and snapshot health",
        description=(
            "Inspect the default .dbgoracle artifacts without mutating the current "
            "debug session."
        ),
    )
    _add_session_arguments(status)
    status.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    status.add_argument("--output", help="Optional output file path")
    status.set_defaults(func=_cmd_status)

    live_status = subparsers.add_parser(
        "live-status",
        help="Inspect the selected live backend without touching real hardware",
        description="Inspect the configured read-only live backend.",
    )
    _add_live_arguments(live_status)
    live_status.set_defaults(func=_cmd_live_status)

    live_registers = subparsers.add_parser(
        "live-registers",
        help="Read registers from the selected live backend",
        description="Read registers from the selected read-only live backend.",
    )
    _add_live_arguments(live_registers)
    live_registers.set_defaults(func=_cmd_live_registers)

    live_memory = subparsers.add_parser(
        "live-memory",
        help="Read bounded memory from the selected live backend",
        description="Read a bounded memory range from the selected read-only live backend.",
    )
    _add_live_arguments(live_memory)
    live_memory.add_argument(
        "--address",
        required=True,
        help="Memory address in decimal or hex notation",
    )
    live_memory.add_argument(
        "--size",
        required=True,
        type=int,
        help="Number of bytes to read",
    )
    live_memory.set_defaults(func=_cmd_live_memory)

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
    capture.set_defaults(func=_cmd_capture_rtt)

    observe = subparsers.add_parser(
        "observe",
        help="Capture and store a reusable snapshot for later report or prompt use",
        description=(
            "Build and store a reusable evidence snapshot from a bounded GDB/MI "
            "transcript plus optional RTT logs."
        ),
    )
    _add_input_arguments(observe, include_snapshot_file=False)
    observe.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve file paths",
    )
    observe.add_argument(
        "--state-out",
        default=None,
        help=(
            "Path for the reusable snapshot JSON written by observe. When omitted, "
            "defaults to the latest_snapshot.json file beside the GDB/MI input, "
            "or falls back to <workspace>/.dbgoracle/latest_snapshot.json."
        ),
    )
    observe.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain in the snapshot",
    )
    observe.set_defaults(func=_cmd_observe)

    snapshot = subparsers.add_parser(
        "snapshot",
        help="Advanced snapshot rendering for automation or low-level inspection",
        description=(
            "Render a snapshot from a saved bundle or bounded raw inputs. Most users "
            "should start with observe, then use report or prompt."
        ),
    )
    _add_input_arguments(snapshot, include_snapshot_file=True)
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
    snapshot.set_defaults(func=_cmd_snapshot)

    prompt = subparsers.add_parser(
        "prompt",
        help="Build a ChatGPT-ready prompt package from a snapshot or raw inputs",
        description=(
            "Package a saved snapshot or bounded raw inputs into a prompt you can "
            "paste into ChatGPT."
        ),
    )
    _add_input_arguments(prompt, include_snapshot_file=True)
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
    prompt.set_defaults(func=_cmd_prompt)

    report = subparsers.add_parser(
        "report",
        help="Render a human-readable evidence report from a snapshot or raw inputs",
        description=(
            "Render a human-readable evidence report from a saved snapshot or bounded "
            "raw inputs."
        ),
    )
    _add_input_arguments(report, include_snapshot_file=True)
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
    report.set_defaults(func=_cmd_report)

    return parser


def _add_session_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve .dbgoracle defaults",
    )
    parser.add_argument(
        "--snapshot-file",
        help="Override the snapshot JSON path",
    )
    parser.add_argument(
        "--gdb-mi",
        help="Override the bounded GDB/MI transcript path",
    )
    parser.add_argument(
        "--rtt",
        help="Override the RTT log path",
    )
    parser.add_argument(
        "--rtt-state",
        help="Override the RTT capture state sidecar path",
    )
    parser.add_argument(
        "--stale-after",
        type=int,
        default=DEFAULT_STALE_AFTER_SECONDS,
        help="Age in seconds after which artifacts are marked stale",
    )


def _add_live_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        default=DEFAULT_LIVE_BACKEND,
        help=f"Live backend selector (available: {', '.join(available_backends())})",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument("--output", help="Optional output file path")


def _add_input_arguments(
    parser: argparse.ArgumentParser,
    include_snapshot_file: bool,
) -> None:
    if include_snapshot_file:
        parser.add_argument(
            "--snapshot-file",
            help="Existing snapshot JSON produced by observe",
        )
    parser.add_argument(
        "--gdb-mi",
        help="Path to a bounded GDB/MI transcript (use - to read from stdin once)",
    )
    parser.add_argument(
        "--gdb-mi-stream",
        action="store_true",
        help="Read bounded GDB/MI data from stdin until EOF (not live-follow mode)",
    )
    parser.add_argument(
        "--rtt",
        help="Path to an RTT log captured alongside the MI transcript",
    )


def _cmd_status(args: argparse.Namespace) -> int:
    config = SessionConfig.from_workspace(
        workspace_root=args.workspace_root,
        snapshot_file=args.snapshot_file,
        gdb_mi_file=args.gdb_mi,
        rtt_file=args.rtt,
        rtt_state_file=args.rtt_state,
        stale_after_seconds=args.stale_after,
    )
    status = collect_session_status(config)
    output = render_session_status(status, fmt=args.format)
    return _emit(output, args.output)


def _cmd_live_status(args: argparse.Namespace) -> int:
    backend = _resolve_live_backend(args.backend)
    output = render_live_status(backend.get_status(), fmt=args.format)
    return _emit(output, args.output)


def _cmd_live_registers(args: argparse.Namespace) -> int:
    backend = _resolve_live_backend(args.backend)
    output = render_register_result(backend.read_registers(), fmt=args.format)
    return _emit(output, args.output)


def _cmd_live_memory(args: argparse.Namespace) -> int:
    backend = _resolve_live_backend(args.backend)
    try:
        address, size = validate_memory_request(args.address, args.size)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    output = render_memory_result(backend.read_memory(address, size), fmt=args.format)
    return _emit(output, args.output)


def _cmd_capture_rtt(args: argparse.Namespace) -> int:
    output_path = Path(args.output).expanduser()
    state_path = (
        Path(args.state_out).expanduser()
        if args.state_out
        else default_state_path(output_path)
    )
    try:
        state = capture_rtt(
            host=args.host,
            port=args.port,
            output_path=output_path,
            state_path=state_path,
            connect_timeout=max(0.0, args.connect_timeout),
            poll_interval=max(0.05, args.poll_interval),
            idle_timeout=args.idle_timeout,
            append=args.append,
            on_connect=lambda _: print(
                f"RTT capture connected {args.host}:{args.port} -> {output_path}"
            ),
        )
    except RttCaptureTimeoutError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError as error:
        print(f"RTT capture failed: {error}", file=sys.stderr)
        return 1

    if state.status == "idle":
        print("RTT capture stopped after reaching the configured idle timeout.")
    elif state.status == "eof":
        print("RTT capture stopped because the RTT server closed the connection.")
    elif state.status == "interrupted":
        print("RTT capture interrupted by user.")
        return 130
    return 0


def _cmd_observe(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    gdb_mi = _resolve_workspace_path(args.gdb_mi, workspace_root)
    rtt = _resolve_workspace_path(args.rtt, workspace_root)
    bundle = _resolve_bundle(args, gdb_mi=gdb_mi, rtt=rtt)
    state_out = _resolve_state_out_path(
        workspace_root=workspace_root,
        requested_state_out=args.state_out,
        gdb_mi=gdb_mi,
        rtt=rtt,
    )
    save_bundle(bundle, state_out)
    print(f"Saved snapshot {bundle.snapshot_id} to {state_out}")
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    bundle = _resolve_bundle(args)
    output = render_snapshot(bundle, fmt=args.format)
    return _emit(output, args.output)


def _cmd_prompt(args: argparse.Namespace) -> int:
    bundle = _resolve_bundle(args, full=args.full)
    intent = _read_intent(args.intent, args.intent_file)
    request = InvestigationRequest(
        goal_text=args.goal,
        intent_text=intent,
        snapshot_ref=bundle.snapshot_id,
        format=args.format,
        detail_level="full" if args.full else "compact",
    )
    output = render_prompt(bundle, request)
    return _emit(output, args.output)


def _cmd_report(args: argparse.Namespace) -> int:
    bundle = _resolve_bundle(args)
    output = render_report(bundle, fmt=args.format)
    return _emit(output, args.output)


def _resolve_bundle(
    args: argparse.Namespace,
    full: bool = False,
    gdb_mi: str | None = None,
    rtt: str | None = None,
):
    gdb_mi = gdb_mi if gdb_mi is not None else getattr(args, "gdb_mi", None)
    rtt = rtt if rtt is not None else getattr(args, "rtt", None)
    snapshot_file = getattr(args, "snapshot_file", None)
    if snapshot_file:
        return load_bundle(snapshot_file)

    if not args.gdb_mi_stream and not gdb_mi:
        raise SystemExit(
            "Either --snapshot-file, --gdb-mi, --gdb-mi-stream, or --gdb-mi - is required."
        )

    rtt_window = FULL_RTT_WINDOW if full else getattr(args, "rtt_window", DEFAULT_RTT_WINDOW)
    if args.gdb_mi_stream:
        rtt_text = _read_rtt(rtt)
        return build_bundle_from_stream(
            sys.stdin,
            rtt_text=rtt_text,
            gdb_source=gdb_mi if gdb_mi else "<stdin>",
            rtt_source=rtt,
            rtt_window=rtt_window,
        )
    if gdb_mi in {"-", "/dev/stdin", "stdin"}:
        rtt_text = _read_rtt(rtt)
        return build_bundle_from_stream(
            sys.stdin,
            rtt_text=rtt_text,
            gdb_source=gdb_mi,
            rtt_source=rtt,
            rtt_window=rtt_window,
        )

    assert gdb_mi is not None
    _require_readable_file(gdb_mi, "GDB/MI")
    if rtt:
        _require_readable_file(rtt, "RTT")
    try:
        return build_bundle_from_files(gdb_mi, rtt, rtt_window=rtt_window)
    except OSError as error:
        raise SystemExit(f"Unable to read one of the required input files: {error}") from error


def _read_rtt(rtt_path: str | None) -> str:
    if not rtt_path:
        return ""
    try:
        return Path(rtt_path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise SystemExit(f"Unable to read RTT file '{rtt_path}': {error}") from error


def _require_readable_file(path: str, label: str) -> None:
    if not os.path.exists(path):
        raise SystemExit(f"{label} file does not exist: {path}")
    if not os.path.isfile(path):
        raise SystemExit(f"{label} path is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise SystemExit(f"{label} file is not readable: {path}")


def _resolve_workspace_path(value: str | None, workspace_root: Path) -> str | None:
    if not value:
        return None
    if value in {"-", "/dev/stdin", "stdin"}:
        return value
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(workspace_root / path)


def _resolve_state_out_path(
    workspace_root: Path,
    requested_state_out: str | None,
    gdb_mi: str | None,
    rtt: str | None,
) -> str:
    if requested_state_out:
        return _resolve_workspace_path(requested_state_out, workspace_root)

    if gdb_mi and gdb_mi not in {"-", "/dev/stdin", "stdin"}:
        return str(Path(gdb_mi).parent / DEFAULT_SNAPSHOT_FILENAME)

    if rtt:
        return str(Path(rtt).parent / DEFAULT_SNAPSHOT_FILENAME)

    return str(workspace_root / DEFAULT_SESSION_DIR / DEFAULT_SNAPSHOT_FILENAME)


def _read_intent(intent: str | None, intent_file: str | None) -> str | None:
    if intent is not None:
        return intent
    if intent_file:
        if intent_file == "-":
            return sys.stdin.read().strip()
        return Path(intent_file).read_text(encoding="utf-8").strip()
    return None


def _resolve_live_backend(name: str):
    try:
        return build_live_backend(name)
    except ValueError as error:
        raise SystemExit(str(error)) from error


def _emit(output: str, path: str | None) -> int:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0
