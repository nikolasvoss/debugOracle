from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "release-readiness.py"
SPEC = importlib.util.spec_from_file_location("release_readiness", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
release_readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_readiness
SPEC.loader.exec_module(release_readiness)


class ReleaseReadinessTests(unittest.TestCase):
    def test_metadata_validation_accepts_current_release_surfaces(self) -> None:
        self.assertEqual(
            release_readiness.metadata_errors(REPOSITORY_ROOT, "v0.3.0"), []
        )

    def test_metadata_validation_rejects_another_tag(self) -> None:
        errors = release_readiness.metadata_errors(REPOSITORY_ROOT, "v0.3.1")

        self.assertEqual(
            errors, ["requested tag v0.3.1 does not match canonical tag v0.3.0"]
        )
