from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import ParseResult, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from packaging.utils import (  # pyright: ignore[reportMissingImports]
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)

from .versioning import VersioningError, compare_versions, satisfies

SUPPORTED_SCHEMA_VERSION = "2"
EXPECTED_PACKAGE_NAME = "debugoracle"
EXPECTED_REPOSITORY = "/nikolasvoss/debugOracle"
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


class ManifestError(ValueError):
    pass


class ManifestNetworkError(OSError):
    pass


class _URLResponse(Protocol):
    headers: Mapping[str, str]

    def read(self, size: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def __enter__(self) -> "_URLResponse": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...


@dataclass(slots=True)
class ReleaseManifest:
    schema_version: str
    channel: str
    package_name: str
    version: str
    python_requires: str
    installer_min_version: str
    artifact_url: str
    artifact_sha256: str
    artifact_kind: str
    artifact_size: int | None = None
    release_notes_url: str | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "ReleaseManifest":
        allowed = {
            "schema_version",
            "channel",
            "package_name",
            "version",
            "python_requires",
            "installer_min_version",
            "artifact_url",
            "artifact_sha256",
            "artifact_kind",
            "artifact_size",
            "release_notes_url",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ManifestError(
                f"Manifest contains unknown fields: {', '.join(unknown)}"
            )
        required = [
            "schema_version",
            "channel",
            "package_name",
            "version",
            "python_requires",
            "installer_min_version",
            "artifact_url",
            "artifact_sha256",
            "artifact_kind",
        ]
        missing = [
            key
            for key in required
            if not isinstance(payload.get(key), str)
            or not str(payload.get(key)).strip()
        ]
        if missing:
            raise ManifestError(
                f"Manifest missing required string fields: {', '.join(missing)}"
            )
        release_notes_url = payload.get("release_notes_url")
        if release_notes_url is not None and not isinstance(release_notes_url, str):
            raise ManifestError(
                "Manifest field release_notes_url must be a string when provided"
            )
        schema_version = str(payload["schema_version"])
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ManifestError(
                f"Unsupported manifest schema version '{schema_version}'."
            )
        package_name = str(payload["package_name"])
        if canonicalize_name(package_name) != EXPECTED_PACKAGE_NAME:
            raise ManifestError(
                f"Unexpected manifest package identity '{package_name}'."
            )
        artifact_kind = str(payload["artifact_kind"])
        if artifact_kind != "wheel":
            raise ManifestError(
                f"Unsupported installer artifact kind '{artifact_kind}'."
            )
        artifact_sha256 = str(payload["artifact_sha256"])
        if _SHA256_PATTERN.fullmatch(artifact_sha256) is None:
            raise ManifestError(
                "Manifest artifact_sha256 must be a 64-digit hex digest."
            )
        artifact_size_value = payload.get("artifact_size")
        if artifact_size_value is not None and (
            isinstance(artifact_size_value, bool)
            or not isinstance(artifact_size_value, int)
            or artifact_size_value <= 0
        ):
            raise ManifestError("Manifest artifact_size must be a positive integer.")
        version = str(payload["version"])
        python_requires = str(payload["python_requires"])
        installer_min_version = str(payload["installer_min_version"])
        try:
            compare_versions(version, version)
            compare_versions(installer_min_version, installer_min_version)
            satisfies("3.10", python_requires)
        except VersioningError as error:
            raise ManifestError(f"Invalid manifest version policy: {error}") from error
        artifact_url = str(payload["artifact_url"])
        _validate_release_wheel_url(artifact_url, package_name, version)
        return cls(
            schema_version=schema_version,
            channel=str(payload["channel"]),
            package_name=package_name,
            version=version,
            python_requires=python_requires,
            installer_min_version=installer_min_version,
            artifact_url=artifact_url,
            artifact_sha256=artifact_sha256.lower(),
            artifact_kind=artifact_kind,
            artifact_size=artifact_size_value,
            release_notes_url=release_notes_url,
        )


def _validate_release_wheel_url(url: str, package_name: str, version: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not _uses_default_https_port(parsed)
    ):
        raise ManifestError("Manifest artifact_url must use HTTPS on github.com.")
    expected_prefix = f"{EXPECTED_REPOSITORY}/releases/download/v{version}/"
    if not parsed.path.startswith(expected_prefix) or parsed.query or parsed.fragment:
        raise ManifestError(
            "Manifest artifact_url must identify this project's versioned GitHub Release."
        )
    filename = Path(unquote(parsed.path)).name
    try:
        wheel_name, wheel_version, _build, _tags = parse_wheel_filename(filename)
    except InvalidWheelFilename as error:
        raise ManifestError(
            f"Manifest artifact is not a valid wheel: {error}"
        ) from error
    if canonicalize_name(package_name) != wheel_name or str(wheel_version) != version:
        raise ManifestError(
            "Manifest artifact filename does not match package name and version."
        )


class ManifestFetcher:
    MAX_MANIFEST_BYTES = 64 * 1024

    def fetch(self, manifest_url: str) -> ReleaseManifest:
        payload = self.fetch_payload(manifest_url)
        return ReleaseManifest.from_mapping(payload)

    def fetch_payload(self, manifest_url: str) -> dict[str, object]:
        parsed = urlparse(manifest_url)
        if parsed.scheme and parsed.scheme not in {"file", "https"}:
            raise ManifestError(f"Unsupported manifest URL scheme '{parsed.scheme}'.")
        try:
            if parsed.scheme in {"", "file"}:
                path = Path(parsed.path if parsed.scheme == "file" else manifest_url)
                raw = path.read_bytes()
                if len(raw) > self.MAX_MANIFEST_BYTES:
                    raise ManifestError("Installer manifest exceeds the size limit.")
            else:
                _validate_manifest_remote_url(manifest_url)
                with self._open_remote(manifest_url) as response:
                    final_url = cast(str, response.geturl())
                    _validate_manifest_remote_url(final_url)
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            declared_size = int(content_length)
                        except ValueError as error:
                            raise ManifestError(
                                "Manifest response has an invalid Content-Length."
                            ) from error
                        if declared_size > self.MAX_MANIFEST_BYTES:
                            raise ManifestError(
                                "Installer manifest exceeds the size limit."
                            )
                    raw = response.read(self.MAX_MANIFEST_BYTES + 1)
                    if len(raw) > self.MAX_MANIFEST_BYTES:
                        raise ManifestError(
                            "Installer manifest exceeds the size limit."
                        )
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ManifestError("Installer manifest JSON must be an object.")
            return payload
        except ManifestError:
            raise
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ManifestError(f"Manifest is not valid JSON: {error}") from error
        except OSError as error:
            raise ManifestNetworkError(str(error)) from error

    def _open_remote(self, manifest_url: str) -> _URLResponse:
        opener = build_opener(_PolicyRedirectHandler(_validate_manifest_remote_url))
        return cast(
            _URLResponse,
            opener.open(Request(manifest_url), timeout=5.0),  # nosec B310
        )


def _validate_manifest_remote_url(url: str) -> None:
    parsed = urlparse(url)
    expected_suffix = "/release/install-manifest.json"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "raw.githubusercontent.com"
        or not _uses_default_https_port(parsed)
        or not parsed.path.startswith(f"{EXPECTED_REPOSITORY}/")
        or not parsed.path.endswith(expected_suffix)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ManifestError(
            "Remote manifests must use the project-owned raw.githubusercontent.com HTTPS path."
        )


def _uses_default_https_port(parsed: ParseResult) -> bool:
    try:
        return parsed.port in {None, 443}
    except ValueError:
        return False


class _PolicyRedirectHandler(HTTPRedirectHandler):
    def __init__(self, validate_url: Callable[[str], None]) -> None:
        super().__init__()
        self._validate_url = validate_url

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self._validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
