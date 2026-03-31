from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_uninstall_module():
    module_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "install" / "uninstall.py"
    )
    spec = importlib.util.spec_from_file_location("test_uninstall_module", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load uninstall module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UninstallBootstrapTests(unittest.TestCase):
    def test_uninstall_forwards_args_to_uninstall_cli(self) -> None:
        uninstall_module = _load_uninstall_module()
        with patch.object(uninstall_module, "main", return_value=0) as main_mock:
            exit_code = uninstall_module.uninstall(["--format", "json", "--keep-path"])

        self.assertEqual(exit_code, 0)
        forwarded = main_mock.call_args.args[0]
        self.assertEqual(forwarded[0], "uninstall-cli")
        self.assertIn("--format", forwarded)
        self.assertIn("json", forwarded)
        self.assertIn("--keep-path", forwarded)


if __name__ == "__main__":
    unittest.main()
