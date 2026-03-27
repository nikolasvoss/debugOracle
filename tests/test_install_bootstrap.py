from __future__ import annotations

import importlib.util
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


def _load_bootstrap_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "install" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("test_bootstrap_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load bootstrap module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallBootstrapTests(unittest.TestCase):
    def test_bootstrap_uses_manifest_source_without_package_source_override(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        with patch.object(bootstrap_module, "main", return_value=0) as main_mock:
            exit_code = bootstrap_module.bootstrap(["--docs-tools", "none"])

        self.assertEqual(exit_code, 0)
        forwarded = main_mock.call_args.args[0]
        self.assertIn("install-cli", forwarded)
        self.assertIn("--manifest-url", forwarded)
        self.assertNotIn("--package-source", forwarded)

    def test_docs_tool_failure_prompts_and_can_continue(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        with (
            patch.object(bootstrap_module, "_inject_requirements", return_value=False),
            patch.object(bootstrap_module.sys.stdin, "isatty", return_value=True),
            patch("builtins.input", return_value=""),
        ):
            exit_code = bootstrap_module._install_docs_tools(bootstrap_module.DOCS_MODE_DOCLING)

        self.assertEqual(exit_code, 0)

    def test_docs_tool_failure_prompts_and_can_abort(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        with (
            patch.object(bootstrap_module, "_inject_requirements", return_value=False),
            patch.object(bootstrap_module.sys.stdin, "isatty", return_value=True),
            patch("builtins.input", return_value="n"),
        ):
            exit_code = bootstrap_module._install_docs_tools(bootstrap_module.DOCS_MODE_SEMANTIC)

        self.assertEqual(exit_code, 1)

    def test_docs_tool_failure_is_fatal_in_non_interactive_mode(self) -> None:
        bootstrap_module = _load_bootstrap_module()
        stderr = StringIO()
        with (
            patch.object(bootstrap_module, "_inject_requirements", return_value=False),
            patch.object(bootstrap_module.sys.stdin, "isatty", return_value=False),
            patch.object(bootstrap_module, "main", return_value=0),
            redirect_stderr(stderr),
        ):
            exit_code = bootstrap_module.bootstrap(["--docs-tools", "semantic"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Non-interactive mode: failing setup", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
