from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...openocd import (
    OpenOcdProcess,
    discover_openocd_processes,
    find_workspace_openocd_process_matches,
)
from ...session import SessionConfig, collect_session_status


def cmd_guard_openocd_launch(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    status = collect_session_status(SessionConfig.from_workspace(workspace_root))
    if status.readiness.state not in {"prepared", "live"}:
        print(
            "Refusing to launch DebugOracle-owned OpenOCD because workspace setup is not finished: "
            f"{status.readiness.reason} {status.readiness.next_human_action}",
            file=sys.stderr,
        )
        return 2

    processes: list[OpenOcdProcess] = list(discover_openocd_processes())
    matches: tuple[OpenOcdProcess, ...] = find_workspace_openocd_process_matches(
        processes,
        workspace_root=workspace_root,
    )

    if not matches:
        if processes and all(process.cwd is None for process in processes):
            print(
                "Refusing to launch DebugOracle-owned OpenOCD because process discovery could not "
                "safely determine workspace ownership for the existing OpenOCD session(s). Stop "
                "manual OpenOCD sessions such as `make debug`, then retry `DebugOracle: Attach STM32`.",
                file=sys.stderr,
            )
            return 2
        print(
            "OpenOCD preflight: no conflicting workspace-matching OpenOCD session detected."
        )
        return 0
    if len(matches) > 1:
        pids = ", ".join(
            str(match.pid) for match in sorted(matches, key=lambda item: item.pid)
        )
        print(
            "Refusing to launch DebugOracle-owned OpenOCD because multiple workspace-matching "
            f"OpenOCD sessions are already running ({pids}). Stop the manual session(s) first "
            "or rerun the attach launch after cleaning them up.",
            file=sys.stderr,
        )
        return 2

    match = next(iter(matches))
    print(
        "Refusing to launch DebugOracle-owned OpenOCD because a workspace-matching OpenOCD "
        f"session is already running (pid {match.pid}). This usually means `make debug` is "
        "still active. Stop that session first, then retry `DebugOracle: Attach STM32`.",
        file=sys.stderr,
    )
    return 2
