#!/usr/bin/env python3
"""Check read-only local and remote prerequisites before a DebugOracle release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"$', re.MULTILINE)
RELEASE_HEADING_PATTERN = re.compile(
    r"^## \[(?!Unreleased\])([^]]+)\](?:\s+-\s+.+)?$", re.MULTILINE
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(arguments: Sequence[str], repository_root: Path) -> CommandResult:
    """Run one fixed read-only prerequisite command."""
    completed = subprocess.run(
        list(arguments),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def canonical_version(repository_root: Path) -> str:
    """Read the canonical package version without importing project code."""
    version_text = (repository_root / "debugoracle" / "version.py").read_text(
        encoding="utf-8"
    )
    match = VERSION_PATTERN.search(version_text)
    if match is None:
        raise ValueError(
            "debugoracle/version.py has no canonical __version__ assignment"
        )
    return match.group(1)


def metadata_errors(repository_root: Path, requested_tag: str) -> list[str]:
    """Return deterministic release-metadata discrepancies."""
    errors: list[str] = []
    try:
        version = canonical_version(repository_root)
        manifest = json.loads(
            (repository_root / "release" / "install-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        changelog = (repository_root / "changelog.md").read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [f"cannot read release metadata: {error}"]

    expected_tag = f"v{version}"
    if requested_tag != expected_tag:
        errors.append(
            f"requested tag {requested_tag} does not match canonical tag {expected_tag}"
        )
    if manifest.get("version") != version:
        errors.append("release manifest version does not match canonical version")
    if manifest.get("release_notes_url") != (
        f"https://github.com/nikolasvoss/debugOracle/releases/tag/{expected_tag}"
    ):
        errors.append("release manifest notes URL does not match canonical tag")
    if (
        f"/releases/download/{expected_tag}/debugoracle-{version}-py3-none-any.whl"
        not in str(manifest.get("artifact_url"))
    ):
        errors.append("release manifest artifact URL does not match canonical version")
    released_versions = RELEASE_HEADING_PATTERN.findall(changelog)
    if not released_versions or released_versions[0] != version:
        errors.append("newest changelog release does not match canonical version")
    return errors


def command_errors(
    repository_root: Path, requested_tag: str, check_github_auth: bool
) -> list[str]:
    """Return failures from fixed read-only Git and GitHub prerequisite checks."""
    errors: list[str] = []
    status = run_command(("git", "status", "--porcelain"), repository_root)
    if status.returncode != 0:
        errors.append("cannot inspect Git working tree")
    elif status.stdout:
        errors.append("working tree has uncommitted changes")

    upstream = run_command(
        ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
        repository_root,
    )
    if upstream.returncode != 0:
        errors.append("current branch has no upstream tracking branch")
    else:
        distance = run_command(
            ("git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"),
            repository_root,
        )
        if distance.returncode != 0 or distance.stdout.strip() != "0\t0":
            errors.append("current branch is not synchronized with its upstream")

    if check_github_auth:
        authentication = run_command(
            ("gh", "auth", "status", "-h", "github.com"), repository_root
        )
        if authentication.returncode != 0:
            errors.append(
                "GitHub CLI authentication is invalid; run: gh auth login -h github.com"
            )

    local_tag = run_command(
        ("git", "show-ref", "--verify", "--quiet", f"refs/tags/{requested_tag}"),
        repository_root,
    )
    if local_tag.returncode == 0:
        errors.append(f"release tag {requested_tag} already exists locally")
    remote_tag = run_command(
        (
            "git",
            "ls-remote",
            "--exit-code",
            "--tags",
            "origin",
            f"refs/tags/{requested_tag}",
        ),
        repository_root,
    )
    if remote_tag.returncode == 0:
        errors.append(f"release tag {requested_tag} already exists on origin")
    elif remote_tag.returncode not in {2}:
        errors.append("cannot determine whether the release tag exists on origin")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag", help="intended annotated release tag; defaults to v<version>"
    )
    parser.add_argument(
        "--skip-github-auth",
        action="store_true",
        help="skip the GitHub CLI authentication check for offline metadata validation",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        version = canonical_version(REPOSITORY_ROOT)
    except (OSError, ValueError) as error:
        print(f"Release readiness failed: {error}", file=sys.stderr)
        return 1
    tag = arguments.tag or f"v{version}"
    errors = metadata_errors(REPOSITORY_ROOT, tag)
    errors.extend(command_errors(REPOSITORY_ROOT, tag, not arguments.skip_github_auth))
    if errors:
        print("Release readiness: blocked", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Release readiness: ready for {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
