from __future__ import annotations

import importlib.util
import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


def _load_entrypoint_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install"
        / "install_docs_tools.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_install_docs_tools_entrypoint", module_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load install_docs_tools module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallDocsToolingEntrypointTests(unittest.TestCase):
    def test_json_output_contains_structured_fields(self) -> None:
        entrypoint = _load_entrypoint_module()
        outcome = entrypoint.DocsToolingOutcome(
            code="success_installed",
            success=True,
            message="ok",
            selection="docling",
            requirements=["docling"],
            remediation="pipx inject debugoracle docling",
        )
        stdout = StringIO()
        with (
            patch.object(entrypoint, "install_docs_tooling", return_value=outcome),
            redirect_stdout(stdout),
        ):
            exit_code = entrypoint.main(["--docs-tools", "docling", "--format", "json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["success"])
        self.assertEqual(payload["selection"], "docling")
        self.assertEqual(payload["requirements"], ["docling"])

    def test_text_output_prints_remediation_for_failure(self) -> None:
        entrypoint = _load_entrypoint_module()
        outcome = entrypoint.DocsToolingOutcome(
            code="failed_inject",
            success=False,
            message="inject failed",
            selection="semantic",
            requirements=["sentence-transformers", "numpy"],
            remediation="pipx inject debugoracle sentence-transformers numpy",
        )
        stdout = StringIO()
        with (
            patch.object(entrypoint, "install_docs_tooling", return_value=outcome),
            redirect_stdout(stdout),
        ):
            exit_code = entrypoint.main(
                ["--docs-tools", "semantic", "--format", "text"]
            )

        self.assertEqual(exit_code, 1)
        text = stdout.getvalue()
        self.assertIn("inject failed", text)
        self.assertIn("Remediation:", text)
        self.assertIn("pipx inject debugoracle sentence-transformers numpy", text)


if __name__ == "__main__":
    unittest.main()
