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
    STATE_STATUS_CONNECTED,
    RttCaptureTimeoutError,
    load_capture_state,
    capture_rtt,
    default_state_path,
)
from .session import (
    DEFAULT_SESSION_DIR,
    DEFAULT_SNAPSHOT_FILENAME,
    DEFAULT_GDB_MI_FILENAME,
    DEFAULT_RTT_FILENAME,
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
            "Inspect default artifacts in the workspace root or .dbgoracle folder "
            "without mutating the current debug session."
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
        "--state-out",
        default=None,
        help=(
            "Path for the reusable snapshot JSON written by observe. When omitted, "
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
        help="Workspace root used to resolve default file paths",
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
    discovery = _resolve_observe_inputs(args, workspace_root)
    gdb_mi = discovery["gdb_mi"]
    rtt = discovery["rtt"]
    state_out = _resolve_state_out_path(
        workspace_root=workspace_root,
        requested_state_out=args.state_out,
        gdb_mi=gdb_mi,
        rtt=rtt,
    )
    bundle = _resolve_bundle(
        args,
        gdb_mi=gdb_mi,
        rtt=rtt,
        allow_snapshot_fallback=False,
        command_name="observe",
        explicit_gdb=discovery["gdb_mi_explicit"],
        explicit_rtt=discovery["rtt_explicit"],
        export_dir=Path(state_out).parent,
    )
    save_bundle(bundle, state_out)
    _warn_if_connected_no_bytes_rtt_capture(rtt=rtt)
    print(f"Saved snapshot {bundle.snapshot_id} to {state_out}")
    return 0


def _warn_if_connected_no_bytes_rtt_capture(rtt: str | None) -> None:
    if not rtt or rtt in {"-", "/dev/stdin", "stdin"}:
        return
    state_path = default_state_path(Path(rtt).expanduser())
    try:
        state = load_capture_state(state_path)
    except (OSError, ValueError, TypeError, KeyError):
        return
    if state.status == STATE_STATUS_CONNECTED and state.bytes_captured == 0:
        print(
            "Warning: RTT capture is connected but no bytes were recorded yet. "
            "If RTT should be active, check your capture configuration."
        )


def _cmd_snapshot(args: argparse.Namespace) -> int:
    bundle = _resolve_bundle(
        args,
        command_name="snapshot",
    )
    output = render_snapshot(bundle, fmt=args.format)
    return _emit(output, args.output)


def _cmd_prompt(args: argparse.Namespace) -> int:
    bundle = _resolve_bundle(
        args,
        full=args.full,
        command_name="prompt",
    )
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
    bundle = _resolve_bundle(
        args,
        command_name="report",
    )
    output = render_report(bundle, fmt=args.format)
    return _emit(output, args.output)


def _resolve_bundle(
    args: argparse.Namespace,
    full: bool = False,
    gdb_mi: str | None = None,
    rtt: str | None = None,
    *,
    allow_snapshot_fallback: bool = True,
    command_name: str = "snapshot",
    explicit_gdb: bool = False,
    explicit_rtt: bool = False,
    export_dir: Path | None = None,
):
    workspace_root = Path(args.workspace_root).resolve()
    config = _resolve_session_config(args, workspace_root)
    requested_snapshot_file = getattr(args, "snapshot_file", None)
    requested_gdb = gdb_mi if gdb_mi is not None else getattr(args, "gdb_mi", None)
    requested_rtt = rtt if rtt is not None else getattr(args, "rtt", None)
    explicit_gdb = explicit_gdb or (getattr(args, "gdb_mi", None) is not None)
    explicit_rtt = explicit_rtt or (getattr(args, "rtt", None) is not None)

    if requested_snapshot_file:
        resolved_snapshot = _resolve_workspace_path(requested_snapshot_file, workspace_root)
        _emit_discovery_summary(
            command_name,
            {
                "snapshot-file": resolved_snapshot,
            },
            {
                "snapshot-file": False,
            },
        )
        return load_bundle(resolved_snapshot)

    if (
        allow_snapshot_fallback
        and not args.gdb_mi_stream
        and not explicit_gdb
        and not explicit_rtt
    ):
        if config.snapshot_file.exists():
            _emit_discovery_summary(
                command_name,
                {
                    "snapshot-file": str(config.snapshot_file),
                },
                {
                    "snapshot-file": True,
                },
            )
            return load_bundle(str(config.snapshot_file))

    resolved_gdb = None
    resolved_rtt = None
    gdb_discovered = False
    rtt_discovered = False

    if explicit_gdb:
        resolved_gdb = _resolve_workspace_path(requested_gdb, workspace_root)
    elif config.gdb_mi_file.is_file():
        resolved_gdb = str(config.gdb_mi_file)
        gdb_discovered = True
    if explicit_rtt:
        resolved_rtt = _resolve_workspace_path(requested_rtt, workspace_root)
    elif config.rtt_file.is_file():
        resolved_rtt = str(config.rtt_file)
        rtt_discovered = True

    if not args.gdb_mi_stream and resolved_gdb is None and resolved_rtt is None:
        raise SystemExit(
            _missing_inputs_error(
                command_name,
                workspace_root,
                allow_snapshot_fallback,
            )
        )

    gdb_mi = resolved_gdb
    rtt = resolved_rtt

    rtt_window = FULL_RTT_WINDOW if full else getattr(args, "rtt_window", DEFAULT_RTT_WINDOW)
    discovered_inputs = {
        "snapshot-file": False,
        "gdb-mi": gdb_discovered,
        "rtt": rtt_discovered,
    }

    if args.gdb_mi_stream:
        rtt_text = _read_rtt(rtt)
        _emit_discovery_summary(
            command_name,
            {
                "gdb-mi": gdb_mi,
                "rtt": rtt,
            },
            discovered_inputs,
        )
        bundle = build_bundle_from_stream(
            sys.stdin,
            rtt_text=rtt_text,
            gdb_source=gdb_mi if gdb_mi else "<stdin>",
            rtt_source=rtt,
            rtt_window=rtt_window,
            export_raw=args.export_raw,
            export_dir=export_dir or config.snapshot_file.parent,
        )
        _emit_raw_export_notice(command_name, bundle.provenance)
        return bundle
    if gdb_mi in {"-", "/dev/stdin", "stdin"}:
        rtt_text = _read_rtt(rtt)
        _emit_discovery_summary(
            command_name,
            {
                "gdb-mi": gdb_mi,
                "rtt": rtt,
            },
            discovered_inputs,
        )
        bundle = build_bundle_from_stream(
            sys.stdin,
            rtt_text=rtt_text,
            gdb_source=gdb_mi,
            rtt_source=rtt,
            rtt_window=rtt_window,
            export_raw=args.export_raw,
            export_dir=export_dir or config.snapshot_file.parent,
        )
        _emit_raw_export_notice(command_name, bundle.provenance)
        return bundle

    if gdb_mi is not None:
        _require_readable_file(gdb_mi, "GDB/MI")

    _emit_discovery_summary(
        command_name,
        {
            "gdb-mi": gdb_mi,
            "rtt": rtt,
        },
        discovered_inputs,
    )
    if rtt:
        _require_readable_file(rtt, "RTT")
    try:
        bundle = build_bundle_from_files(
            gdb_mi,
            rtt,
            rtt_window=rtt_window,
            export_raw=args.export_raw,
            export_dir=export_dir or config.snapshot_file.parent,
        )
        _emit_raw_export_notice(command_name, bundle.provenance)
        return bundle
    except OSError as error:
        raise SystemExit(f"Unable to read one of the required input files: {error}") from error


def _resolve_session_config(
    args: argparse.Namespace,
    workspace_root: Path,
) -> SessionConfig:
    return SessionConfig.from_workspace(
        workspace_root=workspace_root,
        snapshot_file=getattr(args, "snapshot_file", None),
        gdb_mi_file=getattr(args, "gdb_mi", None),
        rtt_file=getattr(args, "rtt", None),
        rtt_state_file=getattr(args, "rtt_state", None) if hasattr(args, "rtt_state") else None,
    )


def _resolve_observe_inputs(
    args: argparse.Namespace,
    workspace_root: Path,
) -> dict[str, str | None | bool]:
    config = _resolve_session_config(args, workspace_root)
    explicit_gdb = getattr(args, "gdb_mi", None) is not None
    explicit_rtt = getattr(args, "rtt", None) is not None
    gdb_mi = _resolve_workspace_path(
        getattr(args, "gdb_mi", None),
        workspace_root,
    )
    rtt = _resolve_workspace_path(
        getattr(args, "rtt", None),
        workspace_root,
    )
    gdb_mi_discovered = False
    rtt_discovered = False

    if gdb_mi is None and config.gdb_mi_file.is_file():
        gdb_mi = str(config.gdb_mi_file)
        gdb_mi_discovered = True
    if rtt is None and config.rtt_file.exists():
        rtt = str(config.rtt_file)
        rtt_discovered = True

    return {
        "gdb_mi": gdb_mi,
        "rtt": rtt,
        "gdb_mi_discovered": gdb_mi_discovered,
        "rtt_discovered": rtt_discovered,
        "gdb_mi_explicit": explicit_gdb,
        "rtt_explicit": explicit_rtt,
    }


def _missing_inputs_error(
    command_name: str,
    workspace_root: Path,
    allow_snapshot_fallback: bool,
) -> str:
    snapshot_candidates = [
        workspace_root / DEFAULT_SNAPSHOT_FILENAME,
        workspace_root / DEFAULT_SESSION_DIR / DEFAULT_SNAPSHOT_FILENAME,
    ]
    gdb_candidates = [
        workspace_root / DEFAULT_GDB_MI_FILENAME,
        workspace_root / DEFAULT_SESSION_DIR / DEFAULT_GDB_MI_FILENAME,
    ]
    rtt_candidates = [
        workspace_root / DEFAULT_RTT_FILENAME,
        workspace_root / DEFAULT_SESSION_DIR / DEFAULT_RTT_FILENAME,
    ]
    lines = [
        f"{command_name} could not auto-resolve an input source.",
        "Either provide --snapshot-file, --gdb-mi, or --rtt, or run from a workspace with:",
        "  - Snapshot:",
        f"    - {snapshot_candidates[0]}",
        f"    - {snapshot_candidates[1]}",
        "  - GDB/MI:",
        f"    - {gdb_candidates[0]}",
        f"    - {gdb_candidates[1]}",
        "  - RTT:",
        f"    - {rtt_candidates[0]}",
        f"    - {rtt_candidates[1]}",
        "  - At least one of GDB/MI or RTT must be available.",
        f"Workspace root: {workspace_root}",
    ]
    if allow_snapshot_fallback:
        lines.append(
            "Tip: run from a folder with latest_snapshot.json (or .dbgoracle/latest_snapshot.json) "
            "or set --workspace-root."
        )
    else:
        lines.append(
            "Tip: set --gdb-mi, --rtt, or both and run from a workspace with "
            "cortex-debug-shared-mi.log or session.rtt (at workspace root or inside .dbgoracle)."
        )
    return "\n".join(lines)


def _emit_discovery_summary(
    command_name: str,
    values: dict[str, str | None],
    discovered: dict[str, bool],
) -> None:
    discovered_items = [
        (label, value)
        for label, value in values.items()
        if value and discovered.get(label, False)
    ]
    if not discovered_items:
        return
    print(
        f"Auto-discovered input paths for {command_name}:",
        file=sys.stderr,
    )
    for label, value in discovered_items:
        print(f"- {label}: {value}", file=sys.stderr)


def _emit_raw_export_notice(command_name: str, provenance: dict[str, object]) -> None:
    if not provenance.get("raw_exported"):
        return
    print(f"Raw input export for {command_name}:", file=sys.stderr)
    export_root = provenance.get("raw_export_root")
    if export_root:
        print(f"- export root: {export_root}", file=sys.stderr)
    gdb_path = provenance.get("gdb_mi_raw_path")
    if gdb_path:
        print(f"- gdb-mi raw: {gdb_path}", file=sys.stderr)
    rtt_path = provenance.get("rtt_raw_path")
    if rtt_path:
        print(f"- rtt raw: {rtt_path}", file=sys.stderr)


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
