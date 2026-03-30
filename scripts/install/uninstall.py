#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from debugoracle.cli.main import main  # noqa: E402


def uninstall(argv: list[str] | None = None) -> int:
    forwarded = list(argv or sys.argv[1:])
    return main(["uninstall-cli", *forwarded])


if __name__ == "__main__":
    raise SystemExit(uninstall())
