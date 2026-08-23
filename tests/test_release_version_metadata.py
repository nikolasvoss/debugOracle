from __future__ import annotations

import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from debugoracle.cli.main import build_parser
from debugoracle.installer.core import DEFAULT_MANIFEST_URL
from debugoracle.version import __version__


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def validate_release_tag(release_tag: str | None) -> None:
    """Reject a supplied CI tag that does not identify the canonical release."""
    if not release_tag:
        return
    expected_tag = f"v{__version__}"
    if release_tag != expected_tag:
        raise ValueError(
            f"Release tag {release_tag!r} must match canonical version {expected_tag!r}"
        )


class ReleaseVersionMetadataTests(unittest.TestCase):
    def test_canonical_public_alpha_version_is_0_2_0(self) -> None:
        self.assertEqual(__version__, "0.2.0")

    def test_release_version_metadata_is_consistent(self) -> None:
        manifest_path = REPOSITORY_ROOT / "release" / "install-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertEqual(manifest["version"], __version__)
        public_repository_url = "https://github.com/nikolasvoss/ai-debugger-v2"
        self.assertEqual(
            manifest["source_url"],
            f"{public_repository_url}/archive/refs/tags/v{__version__}.tar.gz",
        )
        self.assertEqual(
            manifest["release_notes_url"],
            f"{public_repository_url}/releases/tag/v{__version__}",
        )
        self.assertEqual(
            DEFAULT_MANIFEST_URL,
            (
                "https://raw.githubusercontent.com/nikolasvoss/ai-debugger-v2/"
                "main/release/install-manifest.json"
            ),
        )
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn('version = {attr = "debugoracle.version.__version__"}', pyproject)

    def test_cli_version_uses_canonical_release_version(self) -> None:
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as error, redirect_stdout(stdout):
            build_parser().parse_args(["--version"])

        self.assertEqual(error.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), __version__)

    def test_newest_changelog_release_uses_canonical_version(self) -> None:
        changelog = (REPOSITORY_ROOT / "changelog.md").read_text(encoding="utf-8")
        released_versions = re.findall(
            r"^## \[(?!Unreleased\])([^]]+)\](?:\s+-\s+.+)?$",
            changelog,
            flags=re.MULTILINE,
        )

        self.assertTrue(released_versions, "changelog must contain a released version")
        self.assertEqual(released_versions[0], __version__)

    def test_supplied_ci_release_tag_matches_canonical_version(self) -> None:
        validate_release_tag(os.environ.get("DEBUGORACLE_RELEASE_TAG"))

    def test_release_validation_rejects_mismatched_tag(self) -> None:
        with self.assertRaisesRegex(ValueError, "must match canonical version"):
            validate_release_tag("v0.1.0")

    def test_ci_pins_verified_alpha_environment_and_checks_release_tags(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "quality-and-traceability.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("ubuntu-latest", workflow)
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn('tags: ["v*"]', workflow)
        self.assertIn("DEBUGORACLE_RELEASE_TAG:", workflow)

    def test_readme_separates_verified_and_unverified_environments(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Ubuntu 24.04 LTS x86-64 with Python 3.12", readme)
        self.assertIn("currently unverified", readme)
