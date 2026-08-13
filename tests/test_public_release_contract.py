from __future__ import annotations

import configparser
import os
import re
import subprocess
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = REPO_ROOT / "examples" / "debugoracle-reference-workspaces"


def _tracked_paths(repository: Path) -> set[str]:
    git_environment = os.environ.copy()
    for variable in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        git_environment.pop(variable, None)
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
        env=git_environment,
    )
    return {path.decode("utf-8") for path in completed.stdout.split(b"\0") if path}


class PublicReleaseContractTests(unittest.TestCase):
    def test_required_public_governance_files_exist(self) -> None:
        for filename in ("LICENSE", "SECURITY.md"):
            with self.subTest(filename=filename):
                self.assertTrue((REPO_ROOT / filename).is_file())

    def test_project_license_is_apache_2_0(self) -> None:
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        self.assertIn("http://www.apache.org/licenses/", license_text)

    def test_security_policy_uses_github_private_reporting_without_email(self) -> None:
        security_text = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")

        self.assertIn("## Supported Versions", security_text)
        self.assertIn(
            "https://github.com/nikolasvoss/debugoracle/security/advisories/new",
            security_text,
        )
        self.assertNotIn("mailto:", security_text.casefold())
        self.assertIsNone(
            re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", security_text)
        )

    def test_package_metadata_identifies_public_apache_project(self) -> None:
        pyproject = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = pyproject["project"]

        self.assertEqual(project["license"], "Apache-2.0")
        self.assertEqual(project["readme"], "README.md")
        self.assertEqual(
            project["urls"],
            {
                "Changelog": (
                    "https://github.com/nikolasvoss/debugoracle/blob/main/changelog.md"
                ),
                "Issues": "https://github.com/nikolasvoss/debugoracle/issues",
                "Repository": "https://github.com/nikolasvoss/debugoracle",
            },
        )

    def test_generated_document_sidecars_are_ignored(self) -> None:
        ignore_rules = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore")
            .read_text(encoding="utf-8")
            .splitlines()
        }

        self.assertIn("*.dbgoracle-docs/", ignore_rules)
        self.assertIn("*.dbgoracle-docs.staging/", ignore_rules)

    def test_only_public_reference_submodule_is_required(self) -> None:
        modules = configparser.ConfigParser()
        modules.read(REPO_ROOT / ".gitmodules", encoding="utf-8")

        paths = {modules[section]["path"] for section in modules.sections()}
        urls = {modules[section]["url"] for section in modules.sections()}
        self.assertEqual(paths, {"examples/debugoracle-reference-workspaces"})
        self.assertEqual(
            urls,
            {"https://github.com/nikolasvoss/debugoracle-reference-workspaces"},
        )

    def test_vendor_manual_and_generated_doc_artifacts_are_not_tracked(self) -> None:
        prohibited_pdf_names = {
            "J-Link_Commander_SEGGER_Knowledge_Base.pdf",
            "UM08001_JLink.pdf",
            "stm32l423_reference_manual.pdf",
        }
        offenders: list[str] = []
        for label, repository in (("main", REPO_ROOT), ("reference", REFERENCE_ROOT)):
            for tracked_path in _tracked_paths(repository):
                parts = Path(tracked_path).parts
                if (
                    Path(tracked_path).name in prohibited_pdf_names
                    or Path(tracked_path).name == "embeddings.npy"
                    or any(part.endswith(".dbgoracle-docs") for part in parts)
                    or any(part.endswith("_llm") for part in parts)
                ):
                    offenders.append(f"{label}:{tracked_path}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
