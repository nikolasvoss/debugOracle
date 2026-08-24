from __future__ import annotations

import unittest
from pathlib import Path


class VerifyWorkflowDocsTests(unittest.TestCase):
    def test_quality_workflow_uses_the_authoritative_full_command(self) -> None:
        workflow = Path(".github/workflows/quality-and-traceability.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("./scripts/verify.sh full", workflow)
        self.assertNotIn("run: pre-commit run --all-files", workflow)
        self.assertIn("python -m venv .venv", workflow)
        self.assertIn(
            ".venv/bin/python -m pip install pre-commit bandit pytest-cov",
            workflow,
        )
        self.assertIn('.venv/bin/python -m pip install -e ".[dev]"', workflow)
        self.assertIn(
            'PATH="$PWD/.venv/bin:$PATH" timeout 5m ./scripts/verify.sh full',
            workflow,
        )

    def test_release_ci_defers_private_reference_checkout_until_tag_gate(
        self,
    ) -> None:
        workflow = Path(".github/workflows/quality-and-traceability.yml").read_text(
            encoding="utf-8"
        )

        conditional_checkout = (
            "submodules: ${{ github.ref_type == 'tag' && 'recursive' || 'false' }}"
        )
        self.assertGreaterEqual(workflow.count(conditional_checkout), 3)
        self.assertGreaterEqual(
            workflow.count("DEBUGORACLE_SKIP_PRIVATE_REFERENCE:"), 3
        )
        self.assertIn("tests/test_reference_workspace_samples.py", workflow)
        self.assertIn(
            "--deselect=tests/test_public_release_contract.py::"
            "PublicReleaseContractTests::"
            "test_vendor_manual_and_generated_doc_artifacts_are_not_tracked",
            workflow,
        )
        self.assertIn("if: github.ref_type == 'tag'", workflow)
        self.assertIn("git submodule status --recursive", workflow)
        self.assertIn("compatibility-gate:", workflow)
        self.assertIn(
            'python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]', workflow
        )
        self.assertIn("artifact-gate:", workflow)
        self.assertIn("./scripts/verify-release.sh", workflow)

    def test_readme_clone_instructions_initialize_recursive_submodules(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("git clone --recurse-submodules", readme)
        self.assertIn("git submodule update --init --recursive", readme)

    def test_readme_distinguishes_ci_compatibility_from_verified_environment(
        self,
    ) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("Python 3.10 through 3.14", readme)
        self.assertIn("Ubuntu 24.04 LTS x86-64 with Python 3.12", readme)

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


if __name__ == "__main__":
    unittest.main()
