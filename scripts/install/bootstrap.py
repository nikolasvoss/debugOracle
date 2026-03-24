#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "release" / "install-manifest.json"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from debugoracle.cli.main import main


def bootstrap(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    return main([
        "install-cli",
        "--manifest-url",
        str(MANIFEST_PATH),
        *args,
    ])


if __name__ == "__main__":
    raise SystemExit(bootstrap())
