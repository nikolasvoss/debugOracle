from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from debugoracle.installer.manifest import ReleaseManifest
from debugoracle.installer.source import ArtifactDownloader, ArtifactError


class ArtifactDownloaderTests(unittest.TestCase):
    def test_verified_wheel_is_staged_as_private_local_file(self) -> None:
        content = _wheel_bytes()
        manifest = _manifest(content)
        response = _Response(content, manifest.artifact_url)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                path = ArtifactDownloader().download(manifest, Path(tmpdir))
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_checksum_mismatch_and_oversize_remove_partial_file(self) -> None:
        content = _wheel_bytes()
        for manifest, response in (
            (
                _manifest(content, digest="0" * 64),
                _Response(content, _manifest(content).artifact_url),
            ),
            (
                _manifest(content, size=len(content) - 1),
                _Response(content, _manifest(content).artifact_url),
            ),
        ):
            with self.subTest(size=manifest.artifact_size):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    with patch.object(
                        ArtifactDownloader, "_open_remote", return_value=response
                    ):
                        with self.assertRaises(ArtifactError):
                            ArtifactDownloader().download(manifest, root)
                    self.assertEqual(list(root.iterdir()), [])

    def test_untrusted_redirect_destination_is_rejected_before_write(self) -> None:
        content = _wheel_bytes()
        manifest = _manifest(content)
        for final_url in (
            "https://evil.example/debugoracle.whl",
            "https://release-assets.githubusercontent.com:444/asset.whl",
        ):
            with self.subTest(final_url=final_url):
                response = _Response(content, final_url)
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    with patch.object(
                        ArtifactDownloader, "_open_remote", return_value=response
                    ):
                        with self.assertRaises(ArtifactError):
                            ArtifactDownloader().download(manifest, root)
                    self.assertEqual(list(root.iterdir()), [])

    def test_wheel_metadata_identity_must_match_manifest_before_staging(self) -> None:
        for content in (
            _wheel_bytes(name="other-package"),
            _wheel_bytes(metadata_version="0.1.1"),
        ):
            with self.subTest(content_sha256=hashlib.sha256(content).hexdigest()):
                manifest = _manifest(content)
                response = _Response(content, manifest.artifact_url)

                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    with patch.object(
                        ArtifactDownloader, "_open_remote", return_value=response
                    ):
                        with self.assertRaisesRegex(ArtifactError, "metadata identity"):
                            ArtifactDownloader().download(manifest, root)

                    self.assertEqual(list(root.iterdir()), [])

    def test_wheel_with_unsafe_archive_path_is_rejected_before_staging(self) -> None:
        content = _wheel_bytes(extra_path="../../outside.py")
        manifest = _manifest(content)
        response = _Response(content, manifest.artifact_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                with self.assertRaisesRegex(ArtifactError, "unsafe path"):
                    ArtifactDownloader().download(manifest, root)

            self.assertEqual(list(root.iterdir()), [])

    def test_wheel_with_zip_bomb_expansion_is_rejected_before_staging(self) -> None:
        content = _wheel_bytes(
            extra_path="debugoracle/zeros.bin",
            extra_payload=b"\0" * (2 * 1024 * 1024),
        )
        manifest = _manifest(content)
        response = _Response(content, manifest.artifact_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                with self.assertRaisesRegex(ArtifactError, "expansion ratio"):
                    ArtifactDownloader().download(manifest, root)

            self.assertEqual(list(root.iterdir()), [])

    def test_wheel_must_declare_the_supported_pure_python_tag(self) -> None:
        content = _wheel_bytes(wheel_tag="cp312-cp312-manylinux_2_39_x86_64")
        manifest = _manifest(content)
        response = _Response(content, manifest.artifact_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                with self.assertRaisesRegex(ArtifactError, "pure-Python tag"):
                    ArtifactDownloader().download(manifest, root)

            self.assertEqual(list(root.iterdir()), [])

    def test_wheel_filename_must_use_the_supported_pure_python_tag(self) -> None:
        content = _wheel_bytes()
        manifest = _manifest(
            content,
            artifact_filename=(
                "debugoracle-0.1.0-cp312-cp312-manylinux_2_39_x86_64.whl"
            ),
        )
        response = _Response(content, manifest.artifact_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                with self.assertRaisesRegex(ArtifactError, "filename tag"):
                    ArtifactDownloader().download(manifest, root)

            self.assertEqual(list(root.iterdir()), [])

    def test_wheel_with_duplicate_archive_path_is_rejected_before_staging(self) -> None:
        content = _wheel_bytes(duplicate_path="debugoracle-0.1.0.dist-info/METADATA")
        manifest = _manifest(content)
        response = _Response(content, manifest.artifact_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                with self.assertRaisesRegex(ArtifactError, "duplicate path"):
                    ArtifactDownloader().download(manifest, root)

            self.assertEqual(list(root.iterdir()), [])

    def test_wheel_with_corrupt_payload_is_rejected_before_staging(self) -> None:
        raw = bytearray(
            _wheel_bytes(
                extra_path="debugoracle/payload.bin",
                extra_payload=b"unique-payload-marker",
                compression=zipfile.ZIP_STORED,
            )
        )
        marker_index = raw.index(b"unique-payload-marker")
        raw[marker_index] ^= 0x01
        content = bytes(raw)
        manifest = _manifest(content)
        response = _Response(content, manifest.artifact_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                ArtifactDownloader, "_open_remote", return_value=response
            ):
                with self.assertRaisesRegex(ArtifactError, "valid wheel ZIP"):
                    ArtifactDownloader().download(manifest, root)

            self.assertEqual(list(root.iterdir()), [])


class _Response:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self._payload = payload
        self._position = 0
        self._final_url = final_url
        self.headers: dict[str, str] = {"Content-Length": str(len(payload))}

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._payload) - self._position
        chunk = self._payload[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._final_url

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _manifest(
    content: bytes,
    *,
    digest: str | None = None,
    size: int | None = None,
    artifact_filename: str = "debugoracle-0.1.0-py3-none-any.whl",
) -> ReleaseManifest:
    return ReleaseManifest(
        schema_version="2",
        channel="stable",
        package_name="debugoracle",
        version="0.1.0",
        python_requires=">=3.10",
        installer_min_version="0.1.0",
        artifact_url=(
            "https://github.com/nikolasvoss/ai-debugger-v2/releases/download/"
            f"v0.1.0/{artifact_filename}"
        ),
        artifact_sha256=digest or hashlib.sha256(content).hexdigest(),
        artifact_kind="wheel",
        artifact_size=len(content) if size is None else size,
    )


def _wheel_bytes(
    *,
    name: str = "debugoracle",
    version: str = "0.1.0",
    metadata_version: str | None = None,
    wheel_tag: str = "py3-none-any",
    extra_path: str | None = None,
    extra_payload: bytes | str = "payload",
    duplicate_path: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    buffer = io.BytesIO()
    dist_info = f"debugoracle-{version}.dist-info"
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.4\n"
            f"Name: {name}\n"
            f"Version: {metadata_version or version}\n\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\n"
            "Generator: debugoracle-tests\n"
            "Root-Is-Purelib: true\n"
            f"Tag: {wheel_tag}\n\n",
        )
        archive.writestr("debugoracle/__init__.py", "")
        if extra_path is not None:
            archive.writestr(extra_path, extra_payload)
        if duplicate_path is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(duplicate_path, "duplicate")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
