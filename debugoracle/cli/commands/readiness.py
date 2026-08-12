from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ...readiness import (
    collect_host_readiness,
    collect_session_plan,
    collect_workspace_plan,
)


def cmd_doctor_host(args: argparse.Namespace) -> int:
    report = collect_host_readiness()
    if args.format == "json":
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f"Host readiness: {report.status.value}")
        for item in report.items:
            print(f"- {item.key}: {item.state.value} ({item.detail})")
    return 0


def cmd_workspace_plan(args: argparse.Namespace) -> int:
    try:
        plan = collect_workspace_plan(Path(args.workspace_root))
    except OSError as error:
        print(f"dbgoracle workspace plan: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(plan.as_dict(), indent=2))
    else:
        print(f"Workspace readiness: {plan.status}")
        for key, values in plan.candidates.items():
            print(f"- {key}: {len(values)} candidate(s)")
    return 0


def cmd_session_doctor(args: argparse.Namespace) -> int:
    try:
        plan = collect_session_plan(Path(args.workspace_root))
    except OSError as error:
        print(f"dbgoracle session doctor: {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(plan.as_dict(), indent=2))
    else:
        print(f"Session readiness: {plan.status}")
        for key, value in plan.checks.items():
            print(f"- {key}: {value}")
        print("- target contact: not attempted")
    return 0
