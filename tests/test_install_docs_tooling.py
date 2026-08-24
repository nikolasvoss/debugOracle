from __future__ import annotations

import unittest
from unittest.mock import Mock

from debugoracle.installer.docs_tooling import (
    DOCS_MODE_ALL,
    DOCS_MODE_DOCLING,
    DOCS_MODE_NONE,
    DOCS_MODE_SEMANTIC,
    DocsToolingOutcome,
    install_docs_tooling,
)


class InstallDocsToolingTests(unittest.TestCase):
    def test_docling_profile_is_disabled_before_pipx_access(self) -> None:
        runner = Mock()
        which = Mock(return_value="/usr/bin/pipx")

        outcome = install_docs_tooling(
            DOCS_MODE_DOCLING, runner=runner, which=which, env={}
        )

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.code, "blocked_license_audit")
        self.assertEqual(outcome.selection, DOCS_MODE_DOCLING)
        self.assertEqual(outcome.requirements, [])
        self.assertIn("not supported for the current public alpha", outcome.message)
        self.assertIn("dependency license inventory", outcome.remediation)
        runner.assert_not_called()
        which.assert_not_called()

    def test_all_optional_profiles_are_disabled_by_license_audit(self) -> None:
        for selection in (DOCS_MODE_DOCLING, DOCS_MODE_SEMANTIC, DOCS_MODE_ALL):
            with self.subTest(selection=selection):
                runner = Mock()
                which = Mock(return_value="/usr/bin/pipx")
                outcome = install_docs_tooling(
                    selection, runner=runner, which=which, env={}
                )
                self.assertFalse(outcome.success)
                self.assertEqual(outcome.code, "blocked_license_audit")
                self.assertEqual(outcome.requirements, [])
                self.assertEqual(outcome.selection, selection)
                runner.assert_not_called()
                which.assert_not_called()

    def test_none_profile_skips_without_pipx(self) -> None:
        runner = Mock()
        outcome = install_docs_tooling(
            DOCS_MODE_NONE,
            runner=runner,
            which=Mock(return_value=None),
            env={},
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.code, "success_skipped")
        self.assertEqual(
            outcome.remediation,
            "No optional docs tooling is required for the base CLI.",
        )
        runner.assert_not_called()

    def test_outcome_dict_has_stable_keys(self) -> None:
        outcome = DocsToolingOutcome(
            code="success_installed",
            success=True,
            message="ok",
            selection=DOCS_MODE_DOCLING,
            requirements=["docling"],
            remediation="pipx inject debugoracle docling",
        )

        payload = outcome.as_dict()

        self.assertEqual(
            sorted(payload.keys()),
            ["code", "message", "remediation", "requirements", "selection", "success"],
        )


if __name__ == "__main__":
    unittest.main()
