from __future__ import annotations

import unittest
from types import SimpleNamespace
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
    def test_docling_profile_success_returns_structured_outcome(self) -> None:
        runner = Mock(
            side_effect=[
                SimpleNamespace(
                    returncode=0,
                    stdout='{"venvs":{"debugoracle":{"metadata":{}}}}',
                    stderr="",
                ),
                SimpleNamespace(returncode=0, stdout="", stderr=""),
            ]
        )
        which = Mock(return_value="/usr/bin/pipx")

        outcome = install_docs_tooling(
            DOCS_MODE_DOCLING, runner=runner, which=which, env={}
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.code, "success_installed")
        self.assertEqual(outcome.selection, DOCS_MODE_DOCLING)
        self.assertEqual(outcome.requirements, ["docling"])
        self.assertEqual(outcome.remediation, "pipx inject debugoracle docling")

    def test_profile_requirement_mapping(self) -> None:
        cases: list[tuple[str, list[str]]] = [
            (DOCS_MODE_NONE, []),
            (DOCS_MODE_DOCLING, ["docling"]),
            (DOCS_MODE_SEMANTIC, ["sentence-transformers", "numpy"]),
            (DOCS_MODE_ALL, ["docling", "sentence-transformers", "numpy"]),
        ]
        for selection, requirements in cases:
            with self.subTest(selection=selection):
                runner = Mock(
                    side_effect=[
                        SimpleNamespace(
                            returncode=0,
                            stdout='{"venvs":{"debugoracle":{"metadata":{}}}}',
                            stderr="",
                        ),
                        SimpleNamespace(returncode=0, stdout="", stderr=""),
                    ]
                )
                which = Mock(return_value="/usr/bin/pipx")
                outcome = install_docs_tooling(
                    selection, runner=runner, which=which, env={}
                )
                self.assertEqual(outcome.requirements, requirements)
                self.assertEqual(outcome.selection, selection)
                if selection == DOCS_MODE_NONE:
                    self.assertEqual(runner.call_count, 0)

    def test_missing_pipx_is_blocked(self) -> None:
        outcome = install_docs_tooling(
            "docling", runner=Mock(), which=Mock(return_value=None), env={}
        )

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.code, "blocked_missing_pipx")
        self.assertEqual(outcome.remediation, "Install pipx first, then retry.")

    def test_missing_debugoracle_install_is_blocked(self) -> None:
        runner = Mock(
            return_value=SimpleNamespace(returncode=0, stdout='{"venvs":{}}', stderr="")
        )
        which = Mock(return_value="/usr/bin/pipx")

        outcome = install_docs_tooling("semantic", runner=runner, which=which, env={})

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.code, "blocked_missing_debugoracle")
        self.assertEqual(outcome.remediation, "Run ./scripts/install/linux.sh first.")

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
            "pipx inject debugoracle docling sentence-transformers numpy",
        )
        runner.assert_not_called()

    def test_inject_failure_returns_remediation(self) -> None:
        runner = Mock(
            side_effect=[
                SimpleNamespace(
                    returncode=0,
                    stdout='{"venvs":{"debugoracle":{"metadata":{}}}}',
                    stderr="",
                ),
                SimpleNamespace(returncode=1, stdout="", stderr="boom"),
            ]
        )
        which = Mock(return_value="/usr/bin/pipx")

        outcome = install_docs_tooling(
            DOCS_MODE_SEMANTIC, runner=runner, which=which, env={}
        )

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.code, "failed_inject")
        self.assertEqual(
            outcome.remediation, "pipx inject debugoracle sentence-transformers numpy"
        )
        self.assertEqual(outcome.message, "boom")

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
