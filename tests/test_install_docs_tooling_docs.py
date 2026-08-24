from __future__ import annotations

import unittest
from pathlib import Path


class InstallDocsToolingDocsTests(unittest.TestCase):
    def test_readme_links_to_installation_details(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("docs/guides/installation.md", readme)

    def test_docs_ingestion_marks_optional_installer_profiles_disabled(self) -> None:
        guide = Path("docs/docs-ingestion.md").read_text(encoding="utf-8")

        self.assertIn("disabled for the currently supported installer", guide)
        self.assertNotIn("./scripts/install/linux.sh --docs-tools docling", guide)
        self.assertNotIn("./scripts/install/linux.sh --docs-tools semantic", guide)
        self.assertNotIn("./scripts/install/install-docs-tools.sh", guide)
        self.assertNotIn("pipx inject debugoracle docling", guide)
        self.assertNotIn("pipx inject debugoracle sentence-transformers numpy", guide)


if __name__ == "__main__":
    unittest.main()
