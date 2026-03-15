from __future__ import annotations

import argparse
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
from .models import InvestigationRequest
from .output import render_prompt, render_report, render_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbgoracle",
        description="Passive embedded debug evidence packager for ChatGPT",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    observe = subparsers.add_parser("observe", help="Build and store the latest snapshot")
    _add_input_arguments(observe, require_snapshot=False)
    observe.add_argument(
        "--state-out",
        default=".dbgoracle/latest_snapshot.json",
        help="Path for the stored snapshot JSON",
    )
    observe.add_argument(
        "--rtt-window",
        type=int,
        default=DEFAULT_RTT_WINDOW,
        help="Bounded RTT line window to retain in the snapshot",
    )
    observe.set_defaults(func=_cmd_observe)

    snapshot = subparsers.add_parser("snapshot", help="Render a snapshot")
    _add_input_arguments(snapshot, require_snapshot=False)
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

    prompt = subparsers.add_parser("prompt", help="Build a ChatGPT-ready prompt package")
    _add_input_arguments(prompt, require_snapshot=False)
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

    report = subparsers.add_parser("report", help="Build an evidence-only report")
    _add_input_arguments(report, require_snapshot=False)
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


def _add_input_arguments(parser: argparse.ArgumentParser, require_snapshot: bool) -> None:
    parser.add_argument("--snapshot-file", help="Existing snapshot JSON to load")
    parser.add_argument(
        "--gdb-mi",
        help="Path to a GDB/MI transcript (use - to read from stdin)",
    )
    parser.add_argument("--gdb-mi-stream", action="store_true", help="Read GDB/MI data from stdin")
    parser.add_argument("--rtt", help="Path to an RTT log")


def _cmd_observe(args: argparse.Namespace) -> int:
    bundle = _resolve_bundle(args)
    save_bundle(bundle, args.state_out)
    print(f"Saved snapshot {bundle.snapshot_id} to {args.state_out}")
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


def _resolve_bundle(args: argparse.Namespace, full: bool = False):
    if args.snapshot_file:
        return load_bundle(args.snapshot_file)

    if not args.gdb_mi_stream and not args.gdb_mi:
        raise SystemExit(
            "Either --snapshot-file, --gdb-mi, --gdb-mi-stream, or --gdb-mi - is required."
        )

    rtt_window = FULL_RTT_WINDOW if full else getattr(args, "rtt_window", DEFAULT_RTT_WINDOW)
    if args.gdb_mi_stream:
        rtt_text = _read_rtt(args.rtt)
        return build_bundle_from_stream(
            sys.stdin,
            rtt_text=rtt_text,
            gdb_source=args.gdb_mi if args.gdb_mi else "<stdin>",
            rtt_source=args.rtt,
            rtt_window=rtt_window,
        )
    if args.gdb_mi in {"-", "/dev/stdin", "stdin"}:
        rtt_text = _read_rtt(args.rtt)
        return build_bundle_from_stream(
            sys.stdin,
            rtt_text=rtt_text,
            gdb_source=args.gdb_mi,
            rtt_source=args.rtt,
            rtt_window=rtt_window,
        )
    return build_bundle_from_files(args.gdb_mi, args.rtt, rtt_window=rtt_window)


def _read_rtt(rtt_path: str | None) -> str:
    if not rtt_path:
        return ""
    return Path(rtt_path).read_text(encoding="utf-8", errors="replace")


def _read_intent(intent: str | None, intent_file: str | None) -> str | None:
    if intent is not None:
        return intent
    if intent_file:
        if intent_file == "-":
            return sys.stdin.read().strip()
        return Path(intent_file).read_text(encoding="utf-8").strip()
    return None


def _emit(output: str, path: str | None) -> int:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0
