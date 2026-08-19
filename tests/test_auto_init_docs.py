from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
README = REPOSITORY_ROOT / "README.md"


class AutomaticWorkspaceInitDocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = README.read_text(encoding="utf-8")

    def test_fresh_project_golden_path_and_local_input_paths_are_exact(self) -> None:
        command = (
            "dbgoracle init-workspace --workspace-root . --auto --yes --format json"
        )

        self.assertIn(command, self.readme)
        self.assertIn("docs/vendor/", self.readme)
        self.assertIn(".dbgoracle/<device>.svd", self.readme)
        self.assertIn("requires no embedded toolchain, board, probe", self.readme)
        self.assertIn("`partial` (exit code 2)", self.readme)

    def test_vendor_document_boundary_is_explicit_and_links_official_source(
        self,
    ) -> None:
        official_url = (
            "https://www.st.com/en/microcontrollers-microprocessors/"
            "stm32l4-series/documentation.html"
        )

        self.assertIn(official_url, self.readme)
        self.assertIn("DebugOracle does not silently download", self.readme)
        self.assertIn("limited bundled reference", self.readme)
        self.assertIn("project-owned", self.readme)

    def test_showcase_separates_sources_before_the_conclusion(self) -> None:
        showcase_start = self.readme.index("### What the agent can prove")
        showcase_end = self.readme.index("## PR workflow", showcase_start)
        showcase = self.readme[showcase_start:showcase_end]
        source_labels = (
            "**Recorded observation:**",
            "**Firmware source:**",
            "**Register evidence:**",
            "**Bundled reference:**",
            "**Conclusion:**",
        )

        positions = tuple(showcase.index(label) for label in source_labels)
        self.assertEqual(positions, tuple(sorted(positions)))
        for evidence in (
            "OBS: serial_path=fault code=-2",
            "RCC_USART1CLKSOURCE_HSI",
            "RCC_CCIPR = 0x00000002",
            "USART1_BRR = 0x000002B6",
            "23,055 baud",
        ):
            self.assertIn(evidence, showcase)


if __name__ == "__main__":
    unittest.main()
