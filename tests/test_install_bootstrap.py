from __future__ import annotations

import importlib.util
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


def _load_bootstrap_module():
    module_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "install" / "bootstrap.py"
    )
    spec = importlib.util.spec_from_file_location("test_bootstrap_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load bootstrap module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallBootstrapTests(unittest.TestCase):
    def test_bootstrap_uses_manifest_source_without_package_source_override(
        self,
    ) -> None:
        bootstrap_module = _load_bootstrap_module()
        success = bootstrap_module.DocsToolingOutcome(
            code="success_skipped",
            success=True,
            message="Skipped optional docs tooling setup.",
            selection=bootstrap_module.DOCS_MODE_NONE,
            requirements=[],
            remediation="pipx inject debugoracle docling sentence-transformers numpy",
        )
        with (
            patch.object(bootstrap_module, "main", return_value=0) as main_mock,
            patch.object(
                bootstrap_module, "install_docs_tooling", return_value=success
            ),
        ):
            exit_code = bootstrap_module.bootstrap(["--docs-tools", "none"])

        self.assertEqual(exit_code, 0)
        forwarded = main_mock.call_args.args[0]
        self.assertIn("install-cli", forwarded)
        self.assertIn("--manifest-url", forwarded)
        self.assertNotIn("--package-source", forwarded)

    def test_docs_tool_failure_prompts_and_can_continue(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        failure = bootstrap_module.DocsToolingOutcome(
            code="failed_inject",
            success=False,
            message="boom",
            selection=bootstrap_module.DOCS_MODE_DOCLING,
            requirements=["docling"],
            remediation="pipx inject debugoracle docling",
        )
        with (
            patch.object(
                bootstrap_module, "install_docs_tooling", return_value=failure
            ),
            patch.object(bootstrap_module.sys.stdin, "isatty", return_value=True),
            patch("builtins.input", return_value=""),
        ):
            exit_code = bootstrap_module._install_docs_tools(
                bootstrap_module.DOCS_MODE_DOCLING
            )

        self.assertEqual(exit_code, 0)

    def test_docs_tool_failure_prompts_and_can_abort(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        failure = bootstrap_module.DocsToolingOutcome(
            code="failed_inject",
            success=False,
            message="boom",
            selection=bootstrap_module.DOCS_MODE_SEMANTIC,
            requirements=["sentence-transformers", "numpy"],
            remediation="pipx inject debugoracle sentence-transformers numpy",
        )
        with (
            patch.object(
                bootstrap_module, "install_docs_tooling", return_value=failure
            ),
            patch.object(bootstrap_module.sys.stdin, "isatty", return_value=True),
            patch("builtins.input", return_value="n"),
        ):
            exit_code = bootstrap_module._install_docs_tools(
                bootstrap_module.DOCS_MODE_SEMANTIC
            )

        self.assertEqual(exit_code, 1)

    def test_docs_tool_failure_is_fatal_in_non_interactive_mode(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        failure = bootstrap_module.DocsToolingOutcome(
            code="failed_inject",
            success=False,
            message="boom",
            selection=bootstrap_module.DOCS_MODE_SEMANTIC,
            requirements=["sentence-transformers", "numpy"],
            remediation="pipx inject debugoracle sentence-transformers numpy",
        )
        stderr = StringIO()
        with (
            patch.object(
                bootstrap_module, "install_docs_tooling", return_value=failure
            ),
            patch.object(bootstrap_module.sys.stdin, "isatty", return_value=False),
            patch.object(bootstrap_module, "main", return_value=0),
            redirect_stderr(stderr),
        ):
            exit_code = bootstrap_module.bootstrap(["--docs-tools", "semantic"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Non-interactive mode: failing setup", stderr.getvalue())

    def test_docs_tool_success_delegates_to_shared_backend(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        success = bootstrap_module.DocsToolingOutcome(
            code="success_installed",
            success=True,
            message="Installed docling support.",
            selection=bootstrap_module.DOCS_MODE_DOCLING,
            requirements=["docling"],
            remediation="pipx inject debugoracle docling",
        )
        with (
            patch.object(bootstrap_module, "main", return_value=0),
            patch.object(
                bootstrap_module, "install_docs_tooling", return_value=success
            ) as install_mock,
        ):
            exit_code = bootstrap_module.bootstrap(["--docs-tools", "docling"])

        self.assertEqual(exit_code, 0)
        install_mock.assert_called_once_with(bootstrap_module.DOCS_MODE_DOCLING)


if __name__ == "__main__":
    unittest.main()
