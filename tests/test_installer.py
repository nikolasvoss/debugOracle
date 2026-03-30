from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from debugoracle.installer.core import InstallerCore, InstallerOptions
from debugoracle.installer.manifest import ManifestError, ManifestNetworkError, ReleaseManifest
from debugoracle.installer.outcomes import InstallState, InstallerOutcomeCode
from debugoracle.installer.backend.pipx import PipxError


class InstallerCoreTests(unittest.TestCase):
    def test_manifest_missing_required_fields_is_rejected(self) -> None:
        with self.assertRaises(ManifestError):
            ReleaseManifest.from_mapping({"schema_version": "1"})

    def test_blocked_when_pipx_is_missing(self) -> None:
        installer = InstallerCore(
            backend=_FakeBackend(available=False),
            fetcher=_FakeFetcher(_manifest()),
            env=_env(),
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions())

        self.assertEqual(outcome.code, InstallerOutcomeCode.BLOCKED_MISSING_PIPX)
        self.assertFalse(outcome.success)

    def test_fresh_install_retries_manifest_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            backend = _FakeBackend(
                statuses=[
                    _status(InstallState.NOT_INSTALLED, binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                    _status(InstallState.INSTALLED_SAME_VERSION, "0.1.0", binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                ],
                bin_dir=str(home / ".local" / "bin"),
            )
            installer = InstallerCore(
                backend=backend,
                fetcher=_FakeFetcher(_manifest(), failures=[ManifestNetworkError("timeout")]),
                env=_env(home),
                sleep=lambda _seconds: None,
                input_func=lambda _prompt: "n",
            )

            outcome = installer.run(InstallerOptions(package_source_override=str(home), doctor=False))

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP)
        self.assertEqual(backend.install_calls, [str(home)])
        self.assertEqual(outcome.path_action.profile_path, str(home / ".bashrc"))
        self.assertTrue(outcome.path_action.declined)

    def test_same_version_returns_already_installed(self) -> None:
        env = _env()
        env["PATH"] = env["PATH"] + ":/tmp/fake-bin"
        backend = _FakeBackend(statuses=[_status(InstallState.INSTALLED_SAME_VERSION, "0.1.0")])
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(_manifest()),
            env=env,
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions(doctor=False))

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_ALREADY_INSTALLED)
        self.assertEqual(outcome.installed_version, "0.1.0")

    def test_upgrade_path_uses_upgrade_backend_call(self) -> None:
        backend = _FakeBackend(
            statuses=[
                _status(InstallState.INSTALLED_OLDER_VERSION, "0.0.9"),
                _status(InstallState.INSTALLED_SAME_VERSION, "0.1.0"),
            ]
        )
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(_manifest()),
            env=_env(),
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions(package_source_override="/tmp/src", doctor=False))

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP)
        self.assertEqual(backend.upgrade_calls, [("debugoracle", "/tmp/src")])

    def test_invalid_manifest_stops_without_retrying_install(self) -> None:
        backend = _FakeBackend()
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(error=ManifestError("missing version")),
            env=_env(),
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions())

        self.assertEqual(outcome.code, InstallerOutcomeCode.BLOCKED_MANIFEST)
        self.assertEqual(backend.install_calls, [])

    def test_fresh_install_failure_cleans_up(self) -> None:
        backend = _FakeBackend(statuses=[_status(InstallState.NOT_INSTALLED)], install_error=PipxError("boom"))
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(_manifest()),
            env=_env(),
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions(package_source_override="/tmp/src", doctor=False))

        self.assertEqual(outcome.code, InstallerOutcomeCode.FAILED_INSTALL)
        self.assertEqual(backend.uninstall_calls, ["debugoracle"])

    def test_verify_failure_after_fresh_install_cleans_up(self) -> None:
        backend = _FakeBackend(
            statuses=[_status(InstallState.NOT_INSTALLED)],
            verify_result=(False, "binary missing"),
        )
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(_manifest()),
            env=_env(),
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions(package_source_override="/tmp/src", doctor=False))

        self.assertEqual(outcome.code, InstallerOutcomeCode.FAILED_VERIFY)
        self.assertEqual(backend.uninstall_calls, ["debugoracle"])

    def test_path_prompt_can_apply_profile_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            backend = _FakeBackend(
                statuses=[
                    _status(InstallState.NOT_INSTALLED, binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                    _status(InstallState.INSTALLED_SAME_VERSION, "0.1.0", binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                ],
                bin_dir=str(home / ".local" / "bin"),
            )
            installer = InstallerCore(
                backend=backend,
                fetcher=_FakeFetcher(_manifest()),
                env=_env(home),
                sleep=lambda _seconds: None,
                input_func=lambda _prompt: "yes",
            )
            with patch("debugoracle.installer.core.sys.stdin.isatty", return_value=True):
                outcome = installer.run(InstallerOptions(package_source_override=str(home), doctor=False))

            bashrc = home / ".bashrc"
            content = bashrc.read_text(encoding="utf-8")

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP)
        self.assertTrue(outcome.path_action.applied)
        self.assertIn("# debugoracle-managed-path", content)
        self.assertIn('export PATH="' + str(home / '.local' / 'bin') + ':$PATH"', content)

    def test_existing_legacy_path_line_is_not_rewritten_with_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            bashrc = home / ".bashrc"
            legacy_line = f'export PATH="{home / ".local" / "bin"}:$PATH"'
            bashrc.write_text(f"{legacy_line}\n", encoding="utf-8")
            backend = _FakeBackend(
                statuses=[
                    _status(InstallState.NOT_INSTALLED, binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                    _status(InstallState.INSTALLED_SAME_VERSION, "0.1.0", binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                ],
                bin_dir=str(home / ".local" / "bin"),
            )
            installer = InstallerCore(
                backend=backend,
                fetcher=_FakeFetcher(_manifest()),
                env=_env(home),
                sleep=lambda _seconds: None,
                input_func=lambda _prompt: "yes",
            )
            with patch("debugoracle.installer.core.sys.stdin.isatty", return_value=True):
                outcome = installer.run(InstallerOptions(package_source_override=str(home), doctor=False))

            content = bashrc.read_text(encoding="utf-8")

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP)
        self.assertTrue(outcome.path_action.applied)
        self.assertIn(legacy_line, content)
        self.assertNotIn("# debugoracle-managed-path", content)

    def test_commented_export_line_does_not_block_managed_path_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            bashrc = home / ".bashrc"
            legacy_line = f'export PATH="{home / ".local" / "bin"}:$PATH"'
            bashrc.write_text(f"# {legacy_line}\n", encoding="utf-8")
            backend = _FakeBackend(
                statuses=[
                    _status(InstallState.NOT_INSTALLED, binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                    _status(InstallState.INSTALLED_SAME_VERSION, "0.1.0", binary_path=str(home / ".local" / "bin" / "dbgoracle")),
                ],
                bin_dir=str(home / ".local" / "bin"),
            )
            installer = InstallerCore(
                backend=backend,
                fetcher=_FakeFetcher(_manifest()),
                env=_env(home),
                sleep=lambda _seconds: None,
                input_func=lambda _prompt: "yes",
            )
            with patch("debugoracle.installer.core.sys.stdin.isatty", return_value=True):
                outcome = installer.run(InstallerOptions(package_source_override=str(home), doctor=False))

            content = bashrc.read_text(encoding="utf-8")

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP)
        self.assertTrue(outcome.path_action.applied)
        self.assertIn(f"# {legacy_line}", content)
        self.assertIn("# debugoracle-managed-path", content)
        self.assertIn(legacy_line, content)

    def test_optional_doctor_warns_without_blocking_install(self) -> None:
        backend = _FakeBackend(statuses=[_status(InstallState.NOT_INSTALLED), _status(InstallState.INSTALLED_SAME_VERSION, "0.1.0")])
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(_manifest()),
            env=_env(),
            sleep=lambda _seconds: None,
        )
        with patch("debugoracle.installer.core.shutil.which", return_value=None):
            outcome = installer.run(InstallerOptions(package_source_override="/tmp/src", doctor=True))

        self.assertEqual(outcome.code, InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP)
        self.assertTrue(outcome.doctor_notes)
        self.assertIn("openocd", outcome.doctor_notes[0])

    def test_existing_binary_on_path_with_wrong_version_fails_verification(self) -> None:
        env = _env()
        env["PATH"] = env["PATH"] + ":/tmp/fake-bin"
        backend = _FakeBackend(
            statuses=[_status(InstallState.INSTALLED_SAME_VERSION, "0.1.0")],
            verify_result=(False, "Installed binary reports unexpected version: dbgoracle 0.0.9"),
        )
        installer = InstallerCore(
            backend=backend,
            fetcher=_FakeFetcher(_manifest()),
            env=env,
            sleep=lambda _seconds: None,
        )

        outcome = installer.run(InstallerOptions(doctor=False))

        self.assertEqual(outcome.code, InstallerOutcomeCode.FAILED_VERIFY)
        self.assertIn("unexpected version", outcome.details[0])

    def test_non_linux_platform_returns_structured_block(self) -> None:
        installer = InstallerCore(
            backend=_FakeBackend(),
            fetcher=_FakeFetcher(_manifest()),
            env=_env(),
            sleep=lambda _seconds: None,
        )
        with patch("debugoracle.installer.core.sys.platform", "darwin"):
            outcome = installer.run(InstallerOptions())

        self.assertEqual(outcome.code, InstallerOutcomeCode.BLOCKED_PLATFORM)


class _FakeFetcher:
    def __init__(self, manifest: ReleaseManifest | None = None, failures: list[Exception] | None = None, error: Exception | None = None) -> None:
        self.manifest = manifest
        self.failures = list(failures or [])
        self.error = error
        self.calls = 0

    def fetch(self, manifest_url: str) -> ReleaseManifest:
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.failures:
            raise self.failures.pop(0)
        if self.manifest is None:
            raise AssertionError("manifest missing")
        return self.manifest


class _FakeBackend:
    def __init__(
        self,
        *,
        available: bool = True,
        statuses: list[object] | None = None,
        install_error: Exception | None = None,
        upgrade_error: Exception | None = None,
        uninstall_error: Exception | None = None,
        verify_result: tuple[bool, str] = (True, "dbgoracle 0.1.0"),
        bin_dir: str = "/tmp/fake-bin",
    ) -> None:
        self.available = available
        self.statuses = list(statuses or [_status(InstallState.NOT_INSTALLED)])
        self.install_error = install_error
        self.upgrade_error = upgrade_error
        self.uninstall_error = uninstall_error
        self.verify_result = verify_result
        self._bin_dir = Path(bin_dir)
        self.install_calls: list[str] = []
        self.install_force_calls: list[str] = []
        self.upgrade_calls: list[tuple[str, str | None]] = []
        self.uninstall_calls: list[str] = []

    def is_available(self) -> bool:
        return self.available

    def bin_dir(self) -> Path:
        return self._bin_dir

    def inspect_installation(self, package_name: str, target_version: str):
        if self.statuses:
            return self.statuses.pop(0)
        return _status(InstallState.NOT_INSTALLED)

    def install(self, source_spec: str, *, force: bool = False) -> None:
        self.install_calls.append(source_spec)
        if force:
            self.install_force_calls.append(source_spec)
        if self.install_error is not None:
            raise self.install_error

    def upgrade(self, package_name: str, source_spec: str | None = None) -> None:
        self.upgrade_calls.append((package_name, source_spec))
        if self.upgrade_error is not None:
            raise self.upgrade_error

    def uninstall(self, package_name: str) -> None:
        self.uninstall_calls.append(package_name)
        if self.uninstall_error is not None:
            raise self.uninstall_error

    def verify_cli(
        self,
        binary_name: str,
        *,
        binary_path: str | None = None,
        expected_version: str | None = None,
    ) -> tuple[bool, str]:
        return self.verify_result


class _InstallationStatus:
    def __init__(self, state: InstallState, installed_version: str | None = None, binary_path: str | None = None) -> None:
        self.state = state
        self.installed_version = installed_version
        self.binary_path = binary_path or "/tmp/fake-bin/dbgoracle"


def _status(state: InstallState, installed_version: str | None = None, binary_path: str | None = None) -> _InstallationStatus:
    return _InstallationStatus(state, installed_version, binary_path)


def _manifest() -> ReleaseManifest:
    return ReleaseManifest(
        schema_version="1",
        channel="stable",
        package_name="debugoracle",
        version="0.1.0",
        python_requires=">=3.10",
        installer_min_version="0.1.0",
        release_notes_url="https://example.com/release",
    )


def _env(home: Path | None = None) -> dict[str, str]:
    root = home or Path("/tmp/installer-home")
    return {
        "HOME": str(root),
        "PATH": "/usr/bin:/bin",
        "SHELL": "/bin/bash",
    }


if __name__ == "__main__":
    unittest.main()
