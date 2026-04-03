#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from debugoracle.installer.docs_tooling import (  # noqa: E402
    DOCS_MODE_ALL,
    DOCS_MODE_DOCLING,
    DOCS_MODE_NONE,
    DOCS_MODE_SEMANTIC,
    DocsToolingOutcome,
    install_docs_tooling,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install optional docs tooling dependencies for DebugOracle."
    )
    parser.add_argument(
        "--docs-tools",
        choices=[DOCS_MODE_NONE, DOCS_MODE_DOCLING, DOCS_MODE_SEMANTIC, DOCS_MODE_ALL],
        required=True,
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
    )
    return parser


def _render_text(outcome: DocsToolingOutcome) -> None:
    print(outcome.message)
    print(f"Selection: {outcome.selection}")
    if outcome.requirements:
        print(f"Requirements: {', '.join(outcome.requirements)}")
    if outcome.remediation:
        print(f"Remediation: {outcome.remediation}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    outcome = install_docs_tooling(args.docs_tools)
    if args.format == "json":
        print(json.dumps(outcome.as_dict(), indent=2))
    else:
        _render_text(outcome)
    return 0 if outcome.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
