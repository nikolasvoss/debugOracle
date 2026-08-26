from __future__ import annotations

import json
import tempfile
import unittest
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from debugoracle.installer.backend.pipx import PipxBackend, PipxError
from debugoracle.installer.manifest import (
    ManifestError,
    ManifestFetcher,
    ManifestNetworkError,
    ReleaseManifest,
)
from debugoracle.installer.outcomes import InstallState
from debugoracle.installer.versioning import (
    VersioningError,
    compare_versions,
    satisfies,
)


class PipxBackendTests(unittest.TestCase):
    def test_is_available_follows_which(self) -> None:
        backend = PipxBackend(env={"PATH": "/bin"})
        with patch(
            "debugoracle.installer.backend.pipx.shutil.which", return_value=None
        ):
            self.assertFalse(backend.is_available())
        with patch(
            "debugoracle.installer.backend.pipx.shutil.which", return_value="/bin/pipx"
        ):
            self.assertTrue(backend.is_available())

    def test_bin_dir_prefers_configured_path(self) -> None:
        backend = PipxBackend(env={"PIPX_BIN_DIR": "~/custom-bin", "HOME": "/tmp/home"})
        self.assertEqual(backend.bin_dir(), Path("~/custom-bin").expanduser())

    def test_bin_dir_uses_the_effective_pipx_application_directory(self) -> None:
        backend = PipxBackend(env={"HOME": "/tmp/home"})
        with patch.object(
            backend,
            "_run",
            return_value=SimpleNamespace(stdout="/tmp/effective-pipx-bin\n"),
        ) as run_mock:
            self.assertEqual(backend.bin_dir(), Path("/tmp/effective-pipx-bin"))

        run_mock.assert_called_once_with(
            ["pipx", "environment", "--value", "PIPX_BIN_DIR"]
        )

    def test_inspect_installation_not_installed(self) -> None:
        backend = PipxBackend(env={"HOME": "/tmp/home"})
        with patch.object(backend, "_run_json", return_value={"venvs": {}}):
            status = backend.inspect_installation("debugoracle", "0.2.0")
        self.assertEqual(status.state, InstallState.NOT_INSTALLED)

    def test_inspect_installation_state_transitions(self) -> None:
        backend = PipxBackend(env={"PIPX_BIN_DIR": "/tmp/pipx-bin"})

        with patch.object(
            backend,
            "_run_json",
            return_value={
                "venvs": {
                    "debugoracle": {
                        "metadata": {"main_package": {"package_version": "0.2.0"}}
                    }
                }
            },
        ):
            status_same = backend.inspect_installation("debugoracle", "0.2.0")
        self.assertEqual(status_same.state, InstallState.INSTALLED_SAME_VERSION)

        with patch.object(
            backend,
            "_run_json",
            return_value={
                "venvs": {
                    "debugoracle": {
                        "metadata": {"main_package": {"package_version": "0.1.0"}}
                    }
                }
            },
        ):
            status_old = backend.inspect_installation("debugoracle", "0.2.0")
        self.assertEqual(status_old.state, InstallState.INSTALLED_OLDER_VERSION)

        with patch.object(
            backend,
            "_run_json",
            return_value={
                "venvs": {
                    "debugoracle": {
                        "metadata": {"main_package": {"package_version": "0.3.0"}}
                    }
                }
            },
        ):
            status_new = backend.inspect_installation("debugoracle", "0.2.0")
        self.assertEqual(status_new.state, InstallState.INSTALLED_NEWER_VERSION)

        with patch.object(
            backend,
            "_run_json",
            return_value={"venvs": {"debugoracle": {"metadata": {"main_package": {}}}}},
        ):
            status_progress = backend.inspect_installation("debugoracle", "0.2.0")
        self.assertEqual(status_progress.state, InstallState.INSTALL_IN_PROGRESS)

    def test_inspect_installation_rejects_invalid_pipx_version_metadata(self) -> None:
        backend = PipxBackend(env={"HOME": "/tmp/home"})
        payload = {
            "venvs": {
                "debugoracle": {
                    "metadata": {"main_package": {"package_version": "not-a-version"}}
                }
            }
        }
        with patch.object(backend, "_run_json", return_value=payload):
            with self.assertRaises(PipxError):
                backend.inspect_installation("debugoracle", "0.2.0")

    def test_install_upgrade_and_uninstall_dispatch_to_run(self) -> None:
        backend = PipxBackend(env={"PATH": "/bin"})
        with patch.object(backend, "_run") as run_mock:
            backend.install("debugoracle==0.2.0")
            backend.install("debugoracle==0.2.0", force=True)
            backend.upgrade("debugoracle")
            backend.upgrade("debugoracle", source_spec="/tmp/src")
            backend.uninstall("debugoracle")

        self.assertEqual(
            run_mock.call_args_list,
            [
                unittest.mock.call(["pipx", "install", "debugoracle==0.2.0"]),
                unittest.mock.call(
                    ["pipx", "install", "--force", "debugoracle==0.2.0"]
                ),
                unittest.mock.call(["pipx", "upgrade", "debugoracle"]),
                unittest.mock.call(["pipx", "install", "--force", "/tmp/src"]),
                unittest.mock.call(["pipx", "uninstall", "debugoracle"]),
            ],
        )

    def test_verify_cli_failure_paths_and_success(self) -> None:
        backend = PipxBackend(env={"PATH": "/bin", "PIPX_BIN_DIR": "/tmp/pipx-bin"})
        with (
            patch("debugoracle.installer.backend.pipx.shutil.which", return_value=None),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            ok, message = backend.verify_cli("dbgoracle")
        self.assertFalse(ok)
        self.assertIn("not discoverable", message)

        with patch(
            "debugoracle.installer.backend.pipx.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="boom\n"),
        ):
            ok, message = backend.verify_cli("dbgoracle", binary_path="/tmp/dbgoracle")
        self.assertFalse(ok)
        self.assertEqual(message, "boom")

        with patch(
            "debugoracle.installer.backend.pipx.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0, stdout="dbgoracle 0.1.0", stderr=""
            ),
        ):
            ok, message = backend.verify_cli(
                "dbgoracle", binary_path="/tmp/dbgoracle", expected_version="0.2.0"
            )
        self.assertFalse(ok)
        self.assertIn("unexpected version", message)

        with patch(
            "debugoracle.installer.backend.pipx.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="0.2.0\n", stderr=""),
        ):
            ok, message = backend.verify_cli(
                "dbgoracle", binary_path="/tmp/dbgoracle", expected_version="0.2.0"
            )
        self.assertTrue(ok)
        self.assertEqual(message, "0.2.0")

        with patch(
            "debugoracle.installer.backend.pipx.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="10.2.0\n", stderr=""),
        ):
            ok, message = backend.verify_cli(
                "dbgoracle", binary_path="/tmp/dbgoracle", expected_version="0.2.0"
            )
        self.assertFalse(ok)
        self.assertIn("unexpected version", message)

    def test_run_raises_on_nonzero_exit(self) -> None:
        backend = PipxBackend(env={"PATH": "/bin"})
        with patch(
            "debugoracle.installer.backend.pipx.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="bad"),
        ):
            with self.assertRaises(PipxError):
                backend._run(["pipx", "list", "--json"])

    def test_run_json_rejects_invalid_and_non_mapping_payloads(self) -> None:
        backend = PipxBackend(env={"PATH": "/bin"})
        with patch.object(
            backend, "_run", return_value=SimpleNamespace(stdout="not-json")
        ):
            with self.assertRaises(PipxError):
                backend._run_json(["pipx", "list", "--json"])
        with patch.object(backend, "_run", return_value=SimpleNamespace(stdout="[]")):
            with self.assertRaises(PipxError):
                backend._run_json(["pipx", "list", "--json"])

    def test_pep_440_version_ordering_and_specifiers(self) -> None:
        ordered = [
            "1!0.1.dev1",
            "1!0.1rc1",
            "1!0.1",
            "1!0.1+local",
            "1!0.1.post1",
        ]
        for left, right in pairwise(ordered):
            self.assertLess(compare_versions(left, right), 0)
        self.assertEqual(compare_versions("1.0", "1.0.0"), 0)
        self.assertTrue(satisfies("3.12.0", ">=3.10,<3.13"))
        self.assertFalse(satisfies("3.13.0", ">=3.10,<3.13"))
        with self.assertRaises(VersioningError):
            compare_versions("not-a-version", "1.0")
        with self.assertRaises(VersioningError):
            satisfies("3.12", "not-a-specifier")


class ManifestFetcherTests(unittest.TestCase):
    def test_release_manifest_requires_strings_for_required_and_optional_fields(
        self,
    ) -> None:
        with self.assertRaises(ManifestError):
            ReleaseManifest.from_mapping({"schema_version": "1"})

        payload = {
            "schema_version": "2",
            "channel": "stable",
            "package_name": "debugoracle",
            "version": "0.1.0",
            "python_requires": ">=3.10",
            "installer_min_version": "0.1.0",
            "release_notes_url": "https://github.com/nikolasvoss/debugOracle/releases/tag/v0.1.0",
            "artifact_url": "https://github.com/nikolasvoss/debugOracle/releases/download/v0.1.0/debugoracle-0.1.0-py3-none-any.whl",
            "artifact_sha256": "a" * 64,
            "artifact_kind": "wheel",
            "artifact_size": 1234,
        }
        manifest = ReleaseManifest.from_mapping(payload)
        self.assertEqual(manifest.version, "0.1.0")
        self.assertEqual(manifest.artifact_sha256, "a" * 64)

        bad_optional = dict(payload)
        bad_optional["release_notes_url"] = 123
        with self.assertRaises(ManifestError):
            ReleaseManifest.from_mapping(bad_optional)

        for field, value in (
            ("schema_version", "1"),
            ("package_name", "other-project"),
            ("artifact_kind", "sdist"),
            ("artifact_sha256", "not-a-digest"),
            ("artifact_size", 0),
            ("package_source_override", "/tmp/other-checkout"),
        ):
            invalid = dict(payload)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(ManifestError):
                ReleaseManifest.from_mapping(invalid)

    def test_fetch_payload_from_file_path_and_file_scheme(self) -> None:
        fetcher = ManifestFetcher()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text(json.dumps({"schema_version": "1"}), encoding="utf-8")

            payload_from_path = fetcher.fetch_payload(str(path))
            payload_from_file_uri = fetcher.fetch_payload(path.as_uri())

        self.assertEqual(payload_from_path, {"schema_version": "1"})
        self.assertEqual(payload_from_file_uri, {"schema_version": "1"})

    def test_fetch_payload_normalizes_windows_file_uri_drive_prefix(self) -> None:
        fetcher = ManifestFetcher()
        with patch("debugoracle.installer.manifest.Path") as path_class:
            path_class.return_value.read_bytes.return_value = b'{"schema_version": "1"}'

            payload = fetcher.fetch_payload("file:///C:/temp/manifest.json")

        path_class.assert_called_once_with("C:/temp/manifest.json")
        self.assertEqual(payload, {"schema_version": "1"})

    def test_fetch_payload_rejects_non_https_remote_urls_and_wraps_errors(self) -> None:
        fetcher = ManifestFetcher()
        for url in (
            "ftp://example.com/manifest.json",
            "http://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json",
            "https://example.com/manifest.json",
            "https://raw.githubusercontent.com:444/nikolasvoss/debugOracle/main/release/install-manifest.json",
        ):
            with self.subTest(url=url), self.assertRaises(ManifestError):
                fetcher.fetch_payload(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            path.write_text("{not valid", encoding="utf-8")
            with self.assertRaises(ManifestError):
                fetcher.fetch_payload(str(path))

        with patch(
            "debugoracle.installer.manifest.ManifestFetcher._open_remote",
            side_effect=OSError("network down"),
        ):
            with self.assertRaises(ManifestNetworkError):
                fetcher.fetch_payload(
                    "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"
                )

    def test_fetch_payload_bounds_remote_content_and_rejects_redirect_host(
        self,
    ) -> None:
        fetcher = ManifestFetcher()

        class _Response:
            def __init__(self, payload: bytes, final_url: str) -> None:
                self._payload = payload
                self._final_url = final_url
                self.headers: dict[str, str] = {}

            def read(self, size: int = -1) -> bytes:
                return self._payload if size < 0 else self._payload[:size]

            def geturl(self) -> str:
                return self._final_url

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        with patch(
            "debugoracle.installer.manifest.ManifestFetcher._open_remote",
            return_value=_Response(
                b"{not json",
                "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json",
            ),
        ):
            with self.assertRaises(ManifestError):
                fetcher.fetch_payload(
                    "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"
                )

        with patch(
            "debugoracle.installer.manifest.ManifestFetcher._open_remote",
            return_value=_Response(b"{}", "https://evil.example/manifest.json"),
        ):
            with self.assertRaises(ManifestError):
                fetcher.fetch_payload(
                    "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"
                )

        oversized = b"{" + b" " * (ManifestFetcher.MAX_MANIFEST_BYTES + 1)
        with patch(
            "debugoracle.installer.manifest.ManifestFetcher._open_remote",
            return_value=_Response(
                oversized,
                "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json",
            ),
        ):
            with self.assertRaises(ManifestError):
                fetcher.fetch_payload(
                    "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"
                )

    def test_fetch_payload_https_json_error_and_fetch_success(self) -> None:
        fetcher = ManifestFetcher()

        class _Response:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload
                self.headers: dict[str, str] = {}

            def read(self, size: int = -1) -> bytes:
                return self._payload if size < 0 else self._payload[:size]

            def geturl(self) -> str:
                return "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        full_manifest = {
            "schema_version": "2",
            "channel": "stable",
            "package_name": "debugoracle",
            "version": "0.1.0",
            "python_requires": ">=3.10",
            "installer_min_version": "0.1.0",
            "artifact_url": "https://github.com/nikolasvoss/debugOracle/releases/download/v0.1.0/debugoracle-0.1.0-py3-none-any.whl",
            "artifact_sha256": "a" * 64,
            "artifact_kind": "wheel",
        }
        with patch(
            "debugoracle.installer.manifest.ManifestFetcher._open_remote",
            return_value=_Response(json.dumps(full_manifest).encode("utf-8")),
        ):
            manifest = fetcher.fetch(
                "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"
            )
        self.assertEqual(manifest.channel, "stable")


if __name__ == "__main__":
    unittest.main()
