from __future__ import annotations

import unittest
from pathlib import Path


class InstallDocsToolingDocsTests(unittest.TestCase):
    def test_readme_documents_helper_script_commands(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn(
            "./scripts/install/install-docs-tools.sh --docs-tools docling", readme
        )
        self.assertIn(
            "./scripts/install/install-docs-tools.sh --docs-tools semantic",
            readme,
        )
        self.assertIn(
            "./scripts/install/install-docs-tools.sh --docs-tools all", readme
        )

    def test_docs_ingestion_uses_helper_as_primary_optional_path(self) -> None:
        guide = Path("docs/docs-ingestion.md").read_text(encoding="utf-8")

        self.assertIn(
            "./scripts/install/install-docs-tools.sh --docs-tools docling", guide
        )
        self.assertIn(
            "./scripts/install/install-docs-tools.sh --docs-tools semantic",
            guide,
        )
        self.assertIn("pipx inject debugoracle docling", guide)
        self.assertIn("pipx inject debugoracle sentence-transformers numpy", guide)


if __name__ == "__main__":
    unittest.main()
