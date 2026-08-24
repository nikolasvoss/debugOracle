from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ReleasePackagingTests(unittest.TestCase):
    def test_isolated_build_backend_is_pinned_for_reproducibility(self) -> None:
        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(pyproject["build-system"]["requires"], ["setuptools==84.0.0"])

    def test_project_uses_pep_639_license_metadata_without_legacy_classifier(
        self,
    ) -> None:
        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = pyproject["project"]

        self.assertEqual(project["license"], "Apache-2.0")
        self.assertEqual(project["license-files"], ["LICENSE"])
        self.assertFalse(
            any(
                classifier.startswith("License ::")
                for classifier in project["classifiers"]
            )
        )

    def test_declared_python_range_matches_the_release_compatibility_matrix(
        self,
    ) -> None:
        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(pyproject["project"]["requires-python"], ">=3.10,<3.15")

    def test_pep_440_runtime_uses_the_audited_packaging_dependency(self) -> None:
        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertIn("packaging==26.0", pyproject["project"]["dependencies"])


if __name__ == "__main__":
    unittest.main()
