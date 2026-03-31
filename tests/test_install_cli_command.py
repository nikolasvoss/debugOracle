from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from debugoracle.cli.commands.install_cli import cmd_install_cli
from debugoracle.installer.outcomes import InstallerOutcome, InstallerOutcomeCode, PathAction


class InstallCliCommandTests(unittest.TestCase):
    def test_json_output_includes_path_action_fields(self) -> None:
        outcome = InstallerOutcome(
            code=InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP,
            message="installed",
            version="0.2.0",
            installed_version="0.2.0",
            details=["ok"],
            doctor_notes=["note"],
            path_action=PathAction(
                bin_dir="/tmp/bin",
                profile_path="/tmp/.bashrc",
                export_line='export PATH="/tmp/bin:$PATH"',
                applied=False,
                declined=True,
                error="none",
            ),
        )
        args = SimpleNamespace(
            manifest_url="https://example.com/manifest.json",
            channel="stable",
            package_source=None,
            yes=True,
            no_doctor=False,
            format="json",
        )

        class _Installer:
            def run(self, options):
                self.options = options
                return outcome

        fake_installer = _Installer()
        buffer = io.StringIO()
        with (
            patch(
                "debugoracle.cli.commands.install_cli.create_default_installer",
                return_value=fake_installer,
            ),
            redirect_stdout(buffer),
        ):
            exit_code = cmd_install_cli(args)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["code"], InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP.value)
        self.assertEqual(payload["path_action"]["bin_dir"], "/tmp/bin")
        self.assertEqual(fake_installer.options.channel, "stable")
        self.assertTrue(fake_installer.options.assume_yes)

    def test_text_output_goes_to_stdout_for_success(self) -> None:
        outcome = InstallerOutcome(
            code=InstallerOutcomeCode.SUCCESS_INSTALLED,
            message="install ok",
            version="0.2.0",
            installed_version="0.2.0",
            details=["detail-a", "detail-b"],
            doctor_notes=["doctor-a"],
            path_action=PathAction(
                bin_dir="/tmp/bin",
                profile_path="/tmp/.bashrc",
                export_line='export PATH="/tmp/bin:$PATH"',
            ),
        )
        args = SimpleNamespace(
            manifest_url=None,
            channel="stable",
            package_source="/tmp/src",
            yes=False,
            no_doctor=True,
            format="text",
        )

        class _Installer:
            def run(self, _options):
                return outcome

        stdout = io.StringIO()
        with (
            patch(
                "debugoracle.cli.commands.install_cli.create_default_installer",
                return_value=_Installer(),
            ),
            redirect_stdout(stdout),
        ):
            exit_code = cmd_install_cli(args)

        self.assertEqual(exit_code, 0)
        text = stdout.getvalue()
        self.assertIn("install ok", text)
        self.assertIn("Target version: 0.2.0", text)
        self.assertIn("Installed version: 0.2.0", text)
        self.assertIn("- detail-a", text)
        self.assertIn("PATH directory: /tmp/bin", text)
        self.assertIn("Doctor notes:", text)

    def test_text_output_goes_to_stderr_for_failure(self) -> None:
        outcome = InstallerOutcome(
            code=InstallerOutcomeCode.FAILED_INSTALL,
            message="install failed",
            details=["boom"],
        )
        args = SimpleNamespace(
            manifest_url=None,
            channel="stable",
            package_source=None,
            yes=False,
            no_doctor=False,
            format="text",
        )

        class _Installer:
            def run(self, _options):
                return outcome

        stderr = io.StringIO()
        with (
            patch(
                "debugoracle.cli.commands.install_cli.create_default_installer",
                return_value=_Installer(),
            ),
            redirect_stderr(stderr),
        ):
            exit_code = cmd_install_cli(args)

        self.assertEqual(exit_code, 1)
        self.assertIn("install failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
