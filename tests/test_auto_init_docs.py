from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
README = REPOSITORY_ROOT / "README.md"


class AutomaticWorkspaceInitDocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = README.read_text(encoding="utf-8")

    def test_readme_describes_agent_first_optional_input_folder(self) -> None:
        self.assertIn("debugoracle-input/", self.readme)
        self.assertIn("The folder is not required.", self.readme)
        self.assertIn("Ask me before preparing manuals or datasheets", self.readme)

    def test_readme_explains_document_authorization_and_storage(self) -> None:
        self.assertIn("agent asks permission", self.readme)
        self.assertIn("seconds to several minutes", self.readme)
        self.assertIn(".dbgoracle/documentation-search/", self.readme)

    def test_showcase_is_available_without_hardware(self) -> None:
        self.assertIn("## See it work without hardware", self.readme)
        self.assertIn("peripheral-miscfg", self.readme)


if __name__ == "__main__":
    unittest.main()
