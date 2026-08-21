from __future__ import annotations

import configparser
import json
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


def _tracked_gitlinks(repository: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    gitlinks: set[str] = set()
    for entry in completed.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        if metadata.split(b" ", 1)[0] == b"160000":
            gitlinks.add(path.decode("utf-8"))
    return gitlinks


class PublicReleaseContractTests(unittest.TestCase):
    def test_base_dependency_is_the_audited_pypdf_release(self) -> None:
        pyproject = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(pyproject["project"]["dependencies"], ["pypdf==6.16.1"])

    def test_direct_dependency_license_inventory_matches_package_config(self) -> None:
        pyproject = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        inventory = json.loads(
            (
                REPO_ROOT
                / "docs/audits/public-alpha-p0-python-dependency-licenses.json"
            ).read_text(encoding="utf-8")
        )

        configured = {
            "base": pyproject["project"]["dependencies"],
            **pyproject["project"]["optional-dependencies"],
        }
        inventoried = {
            profile["name"]: [item["requirement"] for item in profile["dependencies"]]
            for profile in inventory["profiles"]
        }
        self.assertEqual(inventoried, configured)
        self.assertEqual(inventory["schema_version"], 1)

        profile_status = {
            profile["name"]: profile["installer_status"]
            for profile in inventory["profiles"]
        }
        self.assertEqual(profile_status["base"], "supported")
        self.assertEqual(profile_status["docling"], "disabled_unresolved_license")
        self.assertEqual(profile_status["semantic"], "disabled_unresolved_license")
        self.assertEqual(profile_status["dev"], "not_an_installer_profile")
        self.assertEqual(
            inventory["composed_installer_profiles"],
            [
                {
                    "name": "all",
                    "members": ["docling", "semantic"],
                    "installer_status": "disabled_unresolved_license",
                }
            ],
        )

        for profile in inventory["profiles"]:
            unresolved_dependencies = [
                item
                for item in profile["dependencies"]
                if item["audit_status"] == "unresolved"
            ]
            if unresolved_dependencies:
                self.assertEqual(
                    profile["installer_status"], "disabled_unresolved_license"
                )
                self.assertTrue(profile["unresolved"])

    def test_third_party_notices_records_python_dependency_decisions(self) -> None:
        notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        self.assertIn("pypdf 6.16.1", notices)
        self.assertIn("BSD-3-Clause", notices)
        self.assertRegex(
            notices,
            r"Docling, semantic, and all are disabled for the 0\.2\.0 supported\s+installer",
        )
        self.assertIn(
            "docs/audits/public-alpha-p0-python-dependency-licenses.json", notices
        )

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
            "https://github.com/nikolasvoss/ai-debugger-v2/security/advisories/new",
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
                    "https://github.com/nikolasvoss/ai-debugger-v2/blob/main/changelog.md"
                ),
                "Issues": "https://github.com/nikolasvoss/ai-debugger-v2/issues",
                "Repository": "https://github.com/nikolasvoss/ai-debugger-v2",
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
        self.assertEqual(
            _tracked_gitlinks(REPO_ROOT),
            {"examples/debugoracle-reference-workspaces"},
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
