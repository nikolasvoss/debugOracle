from __future__ import annotations

import unittest
from pathlib import Path


class VerifyWorkflowDocsTests(unittest.TestCase):
    def test_plan_template_includes_fast_and_full_verification_commands(self) -> None:
        plan_template = Path("docs/workflows/plan-template.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("`./scripts/verify.sh fast`", plan_template)
        self.assertIn("`./scripts/verify.sh full`", plan_template)
        self.assertIn("`pre-commit run --all-files`", plan_template)

    def test_review_checklist_marks_fast_optional_and_full_required(self) -> None:
        checklist = Path("docs/workflows/review-checklist.md").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "`./scripts/verify.sh fast` preflight was run (optional)", checklist
        )
        self.assertIn("`./scripts/verify.sh full` was run", checklist)
        self.assertIn(
            "`pre-commit run --all-files` output/result is attached", checklist
        )

    def test_readme_documents_fast_and_full_verification_commands(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("./scripts/verify.sh fast", readme)
        self.assertIn("./scripts/verify.sh full", readme)


if __name__ == "__main__":
    unittest.main()
