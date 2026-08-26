#!/usr/bin/env python3
"""Render DebugOracle's declared runtime dependencies as pip requirements."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def runtime_requirements(pyproject_path: Path) -> tuple[str, ...]:
    """Return the declared runtime requirements in their project order."""
    with pyproject_path.open("rb") as file_handle:
        project = tomllib.load(file_handle)["project"]
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(
        isinstance(dependency, str) for dependency in dependencies
    ):
        raise ValueError("project.dependencies must be a list of strings")
    return tuple(dependencies)


def main() -> int:
    try:
        requirements = runtime_requirements(REPOSITORY_ROOT / "pyproject.toml")
    except (OSError, ValueError, tomllib.TOMLDecodeError, KeyError) as error:
        print(f"Cannot render runtime requirements: {error}", file=sys.stderr)
        return 1
    print("\n".join(requirements))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
