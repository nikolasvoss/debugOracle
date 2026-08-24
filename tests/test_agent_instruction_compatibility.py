from __future__ import annotations

import unittest
from pathlib import Path


class AgentInstructionCompatibilityTests(unittest.TestCase):
    def test_claude_code_uses_the_canonical_project_instructions(self) -> None:
        claude_instructions = Path("CLAUDE.md").read_text(encoding="utf-8")

        self.assertEqual(claude_instructions, "@AGENTS.md\n")

    def test_readme_names_claude_code_as_a_supported_coding_agent(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("Codex", readme)
        self.assertIn("Claude Code", readme)


if __name__ == "__main__":
    unittest.main()
