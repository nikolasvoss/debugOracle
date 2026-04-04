from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from debugoracle.cli.commands.uninstall_cli import cmd_uninstall_cli
from debugoracle.installer.backend.pipx import PipxError
from debugoracle.installer.outcomes import InstallState


class UninstallCliTests(unittest.TestCase):
    def test_interactive_decline_cancels_uninstall_cleanly(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.INSTALLED_SAME_VERSION, "/tmp/fake-bin"
        )
        args = SimpleNamespace(
            format="text",
            keep_path=True,
            force_legacy_path_cleanup=False,
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            patch(
                "debugoracle.cli.commands.uninstall_cli.sys.stdin.isatty",
                return_value=True,
            ),
            patch("builtins.input", return_value="n"),
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_backend.uninstall_calls, [])
        self.assertIn("cancelled", out.getvalue().lower())

    def test_json_mode_skips_prompt_and_uninstalls(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.INSTALLED_SAME_VERSION, "/tmp/fake-bin"
        )
        args = SimpleNamespace(
            format="json",
            keep_path=True,
            force_legacy_path_cleanup=False,
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            patch("builtins.input") as input_mock,
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["code"], "success_uninstalled")
        self.assertEqual(fake_backend.uninstall_calls, ["debugoracle"])
        input_mock.assert_not_called()

    def test_installed_uninstalls_and_removes_marked_path_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            profile = home / ".bashrc"
            export_line = f'export PATH="{home / ".local" / "bin"}:$PATH"'
            profile.write_text(
                f"# debugoracle-managed-path\n{export_line}\n",
                encoding="utf-8",
            )
            fake_backend = _FakeBackend(
                InstallState.INSTALLED_SAME_VERSION, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json",
                keep_path=False,
                force_legacy_path_cleanup=False,
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ", {"HOME": str(home), "SHELL": "/bin/bash"}, clear=False
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["code"], "success_uninstalled")
            self.assertTrue(payload["path_cleanup"]["applied"])
            self.assertTrue(payload["path_cleanup"]["marker_found"])
            self.assertEqual(fake_backend.uninstall_calls, ["debugoracle"])
            self.assertEqual(profile.read_text(encoding="utf-8"), "")

    def test_not_installed_keeps_legacy_line_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            profile = home / ".bashrc"
            export_line = f'export PATH="{home / ".local" / "bin"}:$PATH"'
            profile.write_text(f"{export_line}\n", encoding="utf-8")
            fake_backend = _FakeBackend(
                InstallState.NOT_INSTALLED, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json",
                keep_path=False,
                force_legacy_path_cleanup=False,
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ", {"HOME": str(home), "SHELL": "/bin/bash"}, clear=False
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["code"], "success_not_installed")
            self.assertFalse(payload["path_cleanup"]["applied"])
            self.assertTrue(payload["path_cleanup"]["legacy_line_found"])
            self.assertIsNotNone(payload["path_cleanup"]["manual_action"])
            self.assertEqual(profile.read_text(encoding="utf-8"), f"{export_line}\n")

    def test_force_legacy_cleanup_removes_unmarked_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            profile = home / ".bashrc"
            export_line = f'export PATH="{home / ".local" / "bin"}:$PATH"'
            profile.write_text(f"{export_line}\n", encoding="utf-8")
            fake_backend = _FakeBackend(
                InstallState.NOT_INSTALLED, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json",
                keep_path=False,
                force_legacy_path_cleanup=True,
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ", {"HOME": str(home), "SHELL": "/bin/bash"}, clear=False
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["path_cleanup"]["applied"])
            self.assertTrue(payload["path_cleanup"]["legacy_line_found"])
            self.assertEqual(profile.read_text(encoding="utf-8"), "")

    def test_marker_cleanup_handles_non_standard_managed_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            profile = home / ".bashrc"
            export_line = f'export PATH="{home / ".local" / "bin"}:$PATH"'
            profile.write_text(
                f"# debugoracle-managed-path\n{export_line}  # local tweak\n",
                encoding="utf-8",
            )
            fake_backend = _FakeBackend(
                InstallState.NOT_INSTALLED, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json",
                keep_path=False,
                force_legacy_path_cleanup=False,
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ", {"HOME": str(home), "SHELL": "/bin/bash"}, clear=False
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["path_cleanup"]["applied"])
            self.assertTrue(payload["path_cleanup"]["marker_found"])
            self.assertEqual(
                profile.read_text(encoding="utf-8"),
                "",
            )

    def test_missing_pipx_returns_blocked_code(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.NOT_INSTALLED, "/tmp/fake-bin", available=False
        )
        args = SimpleNamespace(
            format="json", keep_path=False, force_legacy_path_cleanup=False
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["code"], "blocked_missing_pipx")

    def test_uninstall_failure_returns_error(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.INSTALLED_SAME_VERSION,
            "/tmp/fake-bin",
            uninstall_error=PipxError("boom"),
        )
        args = SimpleNamespace(
            format="json", keep_path=False, force_legacy_path_cleanup=False
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["code"], "failed_uninstall")

    def test_inspect_installation_failure_returns_error(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.NOT_INSTALLED,
            "/tmp/fake-bin",
            inspect_error=PipxError("inspect boom"),
        )
        args = SimpleNamespace(
            format="json", keep_path=False, force_legacy_path_cleanup=False
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["code"], "failed_uninstall")
        self.assertIn("inspect boom", payload["details"][0])

    def test_unknown_shell_skips_profile_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            fake_backend = _FakeBackend(
                InstallState.NOT_INSTALLED, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json", keep_path=False, force_legacy_path_cleanup=False
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ",
                    {"HOME": str(home), "SHELL": "/bin/unknown-shell"},
                    clear=False,
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["path_cleanup"]["skipped"])
            self.assertEqual(payload["path_cleanup"]["profile_path"], None)

    def test_cleanup_failure_returns_failed_profile_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            fake_backend = _FakeBackend(
                InstallState.NOT_INSTALLED, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json", keep_path=False, force_legacy_path_cleanup=False
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ", {"HOME": str(home), "SHELL": "/bin/bash"}, clear=False
                ),
                patch(
                    "debugoracle.cli.commands.uninstall_cli.linux_platform.cleanup_path_line",
                    return_value=SimpleNamespace(
                        applied=False,
                        marker_found=False,
                        legacy_line_found=False,
                        error="write failed",
                        manual_action=None,
                    ),
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["code"], "failed_profile_cleanup")
            self.assertIn("write failed", payload["details"][0])

    def test_keep_path_skips_profile_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            fake_backend = _FakeBackend(
                InstallState.NOT_INSTALLED, str(home / ".local" / "bin")
            )
            args = SimpleNamespace(
                format="json", keep_path=True, force_legacy_path_cleanup=False
            )
            with (
                patch(
                    "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                    return_value=fake_backend,
                ),
                patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
                patch.dict(
                    "os.environ", {"HOME": str(home), "SHELL": "/bin/bash"}, clear=False
                ),
                redirect_stdout(StringIO()) as out,
            ):
                exit_code = cmd_uninstall_cli(args)

            payload = json.loads(out.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["path_cleanup"]["skipped"])

    def test_uninstall_always_targets_default_package_name(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.INSTALLED_SAME_VERSION, "/tmp/fake-bin"
        )
        args = SimpleNamespace(
            format="json",
            keep_path=True,
            force_legacy_path_cleanup=False,
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["code"], "success_uninstalled")
        self.assertEqual(fake_backend.inspect_calls, ["debugoracle"])
        self.assertEqual(fake_backend.uninstall_calls, ["debugoracle"])

    def test_uninstall_ignores_extra_arguments_for_target_resolution(self) -> None:
        fake_backend = _FakeBackend(
            InstallState.INSTALLED_SAME_VERSION, "/tmp/fake-bin"
        )
        args = SimpleNamespace(
            format="json",
            keep_path=True,
            force_legacy_path_cleanup=False,
            manifest_url="https://example.com/manifest.json",
        )
        with (
            patch(
                "debugoracle.cli.commands.uninstall_cli.PipxBackend",
                return_value=fake_backend,
            ),
            patch("debugoracle.cli.commands.uninstall_cli.sys.platform", "linux"),
            redirect_stdout(StringIO()) as out,
        ):
            exit_code = cmd_uninstall_cli(args)

        payload = json.loads(out.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["code"], "success_uninstalled")
        self.assertEqual(fake_backend.inspect_calls, ["debugoracle"])
        self.assertEqual(fake_backend.uninstall_calls, ["debugoracle"])


class _FakeStatus:
    def __init__(self, state: InstallState) -> None:
        self.state = state


class _FakeBackend:
    def __init__(
        self,
        state: InstallState,
        bin_dir: str,
        *,
        available: bool = True,
        uninstall_error: Exception | None = None,
        inspect_error: Exception | None = None,
    ) -> None:
        self.state = state
        self._bin_dir = Path(bin_dir)
        self.available = available
        self.uninstall_error = uninstall_error
        self.inspect_error = inspect_error
        self.inspect_calls: list[str] = []
        self.uninstall_calls: list[str] = []

    def is_available(self) -> bool:
        return self.available

    def inspect_installation(
        self, package_name: str, target_version: str
    ) -> _FakeStatus:
        self.inspect_calls.append(package_name)
        if self.inspect_error is not None:
            raise self.inspect_error
        return _FakeStatus(self.state)

    def uninstall(self, package_name: str) -> None:
        self.uninstall_calls.append(package_name)
        if self.uninstall_error is not None:
            raise self.uninstall_error

    def bin_dir(self) -> Path:
        return self._bin_dir


if __name__ == "__main__":
    unittest.main()
