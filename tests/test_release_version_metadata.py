from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from debugoracle.cli.main import build_parser
from debugoracle.version import __version__


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ReleaseVersionMetadataTests(unittest.TestCase):
    def test_release_version_metadata_is_consistent(self) -> None:
        manifest_path = REPOSITORY_ROOT / "release" / "install-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertEqual(manifest["version"], __version__)
        self.assertEqual(manifest["source_url"], f"debugoracle=={__version__}")
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn('version = {attr = "debugoracle.version.__version__"}', pyproject)

    def test_cli_version_uses_canonical_release_version(self) -> None:
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as error, redirect_stdout(stdout):
            build_parser().parse_args(["--version"])

        self.assertEqual(error.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), __version__)
