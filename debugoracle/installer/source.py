from __future__ import annotations

import hashlib
import os
import re
import stat
import zipfile
from collections.abc import Mapping
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Protocol, Self, cast
from urllib.parse import unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from packaging.utils import (  # pyright: ignore[reportMissingImports]
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)

from .manifest import (
    ManifestError,
    ReleaseManifest,
    _uses_default_https_port,
    _validate_release_wheel_url,
)

_MAX_WHEEL_ENTRIES = 4096
_MAX_WHEEL_ENTRY_BYTES = 64 * 1024 * 1024
_MAX_WHEEL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
_MAX_WHEEL_EXPANSION_RATIO = 200
_MAX_WHEEL_CONTROL_FILE_BYTES = 1024 * 1024


class ArtifactError(ValueError):
    pass


class ArtifactNetworkError(OSError):
    pass


class ArtifactSource(Protocol):
    def download(self, manifest: ReleaseManifest, destination_dir: Path) -> Path: ...


class _URLResponse(Protocol):
    headers: Mapping[str, str]

    def read(self, size: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...


class ArtifactDownloader:
    MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
    CHUNK_BYTES = 64 * 1024

    def download(self, manifest: ReleaseManifest, destination_dir: Path) -> Path:
        try:
            _validate_release_wheel_url(
                manifest.artifact_url, manifest.package_name, manifest.version
            )
        except ManifestError as error:
            raise ArtifactError(str(error)) from error
        if (
            manifest.artifact_size is not None
            and manifest.artifact_size > self.MAX_ARTIFACT_BYTES
        ):
            raise ArtifactError("Release artifact exceeds the download size limit.")

        filename = Path(unquote(urlparse(manifest.artifact_url).path)).name
        destination = destination_dir / filename
        try:
            with self._open_remote(manifest.artifact_url) as response:
                self._validate_response(response, manifest)
                digest = hashlib.sha256()
                total = 0
                with destination.open("xb") as output:
                    os.chmod(destination, 0o600)
                    while True:
                        chunk = response.read(self.CHUNK_BYTES)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.MAX_ARTIFACT_BYTES or (
                            manifest.artifact_size is not None
                            and total > manifest.artifact_size
                        ):
                            raise ArtifactError(
                                "Release artifact exceeds its allowed size."
                            )
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if (
                    manifest.artifact_size is not None
                    and total != manifest.artifact_size
                ):
                    raise ArtifactError(
                        "Release artifact size does not match the manifest."
                    )
                if digest.hexdigest() != manifest.artifact_sha256.lower():
                    raise ArtifactError(
                        "Release artifact SHA-256 does not match the manifest."
                    )
                _validate_wheel_archive(destination, manifest)
            return destination
        except ArtifactError:
            destination.unlink(missing_ok=True)
            raise
        except OSError as error:
            destination.unlink(missing_ok=True)
            raise ArtifactNetworkError(str(error)) from error

    def _validate_response(
        self, response: _URLResponse, manifest: ReleaseManifest
    ) -> None:
        final_url = cast(str, response.geturl())
        _validate_artifact_destination(final_url, manifest)
        content_length = response.headers.get("Content-Length")
        if content_length is None:
            return
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise ArtifactError(
                "Release artifact has an invalid Content-Length."
            ) from error
        if declared_size > self.MAX_ARTIFACT_BYTES:
            raise ArtifactError("Release artifact exceeds the download size limit.")
        if (
            manifest.artifact_size is not None
            and declared_size != manifest.artifact_size
        ):
            raise ArtifactError(
                "Release artifact Content-Length does not match the manifest."
            )

    def _open_remote(self, artifact_url: str) -> _URLResponse:
        opener = build_opener(_ArtifactRedirectHandler())
        return cast(
            _URLResponse,
            opener.open(Request(artifact_url), timeout=15.0),  # nosec B310
        )


def _validate_artifact_destination(url: str, manifest: ReleaseManifest) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not _uses_default_https_port(parsed)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ArtifactError(
            "Release artifact redirects must remain on trusted HTTPS URLs."
        )
    if parsed.hostname == "github.com":
        try:
            _validate_release_wheel_url(url, manifest.package_name, manifest.version)
        except ManifestError as error:
            raise ArtifactError(str(error)) from error
        return
    if parsed.hostname not in {
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }:
        raise ArtifactError("Release artifact redirected to an untrusted host.")


class _ArtifactRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urlparse(newurl)
        if (
            parsed.scheme != "https"
            or not _uses_default_https_port(parsed)
            or parsed.hostname
            not in {
                "github.com",
                "objects.githubusercontent.com",
                "release-assets.githubusercontent.com",
            }
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ArtifactError(
                "Release artifact redirected to an untrusted destination."
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_wheel_archive(path: Path, manifest: ReleaseManifest) -> None:
    filename = Path(unquote(urlparse(manifest.artifact_url).path)).name
    try:
        _name, _version, _build, filename_tags = parse_wheel_filename(filename)
    except InvalidWheelFilename as error:
        raise ArtifactError(
            f"Release artifact has an invalid wheel filename: {error}"
        ) from error
    if {str(tag) for tag in filename_tags} != {"py3-none-any"}:
        raise ArtifactError(
            "Release wheel filename tag must be the supported py3-none-any tag."
        )
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            _validate_archive_entries(entries)
            corrupt_entry = archive.testzip()
            if corrupt_entry is not None:
                raise ArtifactError(
                    "Release artifact is not a valid wheel ZIP: "
                    f"corrupt entry {corrupt_entry!r}."
                )
            metadata_entries = [
                info
                for info in entries
                if info.filename.endswith(".dist-info/METADATA")
            ]
            if len(metadata_entries) != 1:
                raise ArtifactError(
                    "Release wheel must contain exactly one dist-info/METADATA file."
                )
            if metadata_entries[0].file_size > _MAX_WHEEL_CONTROL_FILE_BYTES:
                raise ArtifactError("Release wheel METADATA exceeds the size limit.")
            expected_dist_info = (
                f"{_wheel_distribution_component(manifest.package_name)}-"
                f"{_wheel_version_component(manifest.version)}.dist-info"
            )
            if metadata_entries[0].filename != f"{expected_dist_info}/METADATA":
                raise ArtifactError(
                    "Release wheel dist-info identity does not match the manifest."
                )
            metadata = BytesParser(policy=policy.default).parsebytes(
                archive.read(metadata_entries[0]), headersonly=True
            )
            wheel_entries = [
                info for info in entries if info.filename.endswith(".dist-info/WHEEL")
            ]
            if len(wheel_entries) != 1 or wheel_entries[0].filename != (
                f"{expected_dist_info}/WHEEL"
            ):
                raise ArtifactError(
                    "Release wheel must contain exactly one matching dist-info/WHEEL file."
                )
            if wheel_entries[0].file_size > _MAX_WHEEL_CONTROL_FILE_BYTES:
                raise ArtifactError(
                    "Release wheel WHEEL metadata exceeds the size limit."
                )
            wheel_metadata = BytesParser(policy=policy.default).parsebytes(
                archive.read(wheel_entries[0]), headersonly=True
            )
    except ArtifactError:
        raise
    except (
        OSError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as error:
        raise ArtifactError(
            f"Release artifact is not a valid wheel ZIP: {error}"
        ) from error

    metadata_name = metadata.get("Name")
    metadata_version = metadata.get("Version")
    if (
        not isinstance(metadata_name, str)
        or canonicalize_name(metadata_name) != canonicalize_name(manifest.package_name)
        or metadata_version != manifest.version
    ):
        raise ArtifactError(
            "Release wheel metadata identity does not match the manifest package and version."
        )
    wheel_tags = wheel_metadata.get_all("Tag", [])
    if (
        wheel_metadata.get("Root-Is-Purelib", "").strip().lower() != "true"
        or wheel_metadata.get("Wheel-Version", "").split(".", 1)[0] != "1"
        or wheel_tags != ["py3-none-any"]
    ):
        raise ArtifactError(
            "Release wheel must declare the supported py3-none-any pure-Python tag."
        )


def _validate_archive_entries(entries: list[zipfile.ZipInfo]) -> None:
    if len(entries) > _MAX_WHEEL_ENTRIES:
        raise ArtifactError("Release wheel contains too many archive entries.")
    seen: set[str] = set()
    uncompressed_total = 0
    for entry in entries:
        name = entry.filename
        parts = name.split("/")
        path_parts = parts[:-1] if name.endswith("/") else parts
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or any(part in {"", ".", ".."} for part in path_parts)
            or (parts and ":" in parts[0])
        ):
            raise ArtifactError(f"Release wheel contains an unsafe path: {name!r}.")
        if name in seen:
            raise ArtifactError(f"Release wheel contains a duplicate path: {name!r}.")
        seen.add(name)
        if entry.flag_bits & 0x1:
            raise ArtifactError("Release wheel contains an encrypted entry.")
        if entry.file_size > _MAX_WHEEL_ENTRY_BYTES:
            raise ArtifactError(
                f"Release wheel entry exceeds the size limit: {name!r}."
            )
        uncompressed_total += entry.file_size
        if uncompressed_total > _MAX_WHEEL_UNCOMPRESSED_BYTES:
            raise ArtifactError("Release wheel uncompressed size exceeds the limit.")
        if (
            entry.file_size > _MAX_WHEEL_CONTROL_FILE_BYTES
            and entry.file_size / max(1, entry.compress_size)
            > _MAX_WHEEL_EXPANSION_RATIO
        ):
            raise ArtifactError(
                f"Release wheel entry has an unsafe expansion ratio: {name!r}."
            )
        unix_mode = (entry.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(unix_mode)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ArtifactError(
                f"Release wheel contains a non-regular archive entry: {name!r}."
            )


def _wheel_distribution_component(value: str) -> str:
    return re.sub(r"[-_.]+", "_", value)


def _wheel_version_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "_", value)
