from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...renderers.status import render_session_status
from ...safe_io import atomic_write_text
from ...session import SessionConfig, collect_session_status
from ...sources.streams.rtt import (
    RttCaptureTimeoutError,
    capture_rtt,
    default_state_path,
)


def cmd_status(args: argparse.Namespace) -> int:
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
    return emit(output, args.output)


def cmd_capture_rtt(args: argparse.Namespace) -> int:
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


def emit(output: str, path: str | None) -> int:
    if path:
        target = Path(path)
        try:
            atomic_write_text(target, output)
        except OSError as error:
            print(f"Could not safely write output: {error}", file=sys.stderr)
            return 1
    else:
        print(output, end="")
    return 0
