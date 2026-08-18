from __future__ import annotations

import unittest
from pathlib import Path


class InstallDocsToolingDocsTests(unittest.TestCase):
    def test_readme_documents_linux_installer_docs_tools_commands(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("./scripts/install/linux.sh --docs-tools docling", readme)
        self.assertIn(
            "./scripts/install/linux.sh --docs-tools semantic",
            readme,
        )
        self.assertIn("./scripts/install/linux.sh --docs-tools all", readme)
        self.assertNotIn("./scripts/install/install-docs-tools.sh", readme)

    def test_docs_ingestion_marks_optional_installer_profiles_disabled(self) -> None:
        guide = Path("docs/docs-ingestion.md").read_text(encoding="utf-8")

        self.assertIn("disabled for the 0.2.0 supported installer", guide)
        self.assertNotIn("./scripts/install/linux.sh --docs-tools docling", guide)
        self.assertNotIn("./scripts/install/linux.sh --docs-tools semantic", guide)
        self.assertNotIn("./scripts/install/install-docs-tools.sh", guide)
        self.assertNotIn("pipx inject debugoracle docling", guide)
        self.assertNotIn("pipx inject debugoracle sentence-transformers numpy", guide)


if __name__ == "__main__":
    unittest.main()
