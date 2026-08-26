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
        version = release_readiness.canonical_version(REPOSITORY_ROOT)

        self.assertEqual(
            release_readiness.metadata_errors(REPOSITORY_ROOT, f"v{version}"), []
        )

    def test_metadata_validation_rejects_another_tag(self) -> None:
        version = release_readiness.canonical_version(REPOSITORY_ROOT)
        invalid_tag = "not-a-release-tag"
        errors = release_readiness.metadata_errors(REPOSITORY_ROOT, invalid_tag)

        self.assertEqual(
            errors,
            [f"requested tag {invalid_tag} does not match canonical tag v{version}"],
        )
