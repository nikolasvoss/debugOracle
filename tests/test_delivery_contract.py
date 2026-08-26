from __future__ import annotations

import unittest
from pathlib import Path


class DeliveryContractTests(unittest.TestCase):
    def test_task_spec_template_requires_delivery_evidence_for_relevant_work(
        self,
    ) -> None:
        template = Path("docs/workflows/task-spec-template.md").read_text(
            encoding="utf-8"
        )
        workflow = Path("docs/workflows/AGENT_WORKFLOW_RULES.md").read_text(
            encoding="utf-8"
        )

        for required_field in (
            "Supported execution environments",
            "Adversarial boundary cases",
            "Release and operational prerequisites",
        ):
            self.assertIn(required_field, template)
        self.assertIn("Delivery Contract", workflow)

    def test_workflow_routes_runtime_audit_through_checked_in_helper(self) -> None:
        workflow = Path(".github/workflows/quality-and-traceability.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("python scripts/render-runtime-requirements.py", workflow)
        self.assertNotIn("python -c 'import tomllib; print(*tomllib.load", workflow)

    def test_release_documentation_names_required_native_checks(self) -> None:
        documentation = Path("docs/guides/release-readiness.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("installer-platform-gate (macos-latest)", documentation)
        self.assertIn("installer-platform-gate (windows-latest)", documentation)
