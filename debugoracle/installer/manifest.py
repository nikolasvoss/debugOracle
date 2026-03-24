from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


class ManifestError(ValueError):
    pass


class ManifestNetworkError(OSError):
    pass


@dataclass(slots=True)
class ReleaseManifest:
    schema_version: str
    channel: str
    package_name: str
    version: str
    python_requires: str
    installer_min_version: str
    release_notes_url: str | None = None
    source_url: str | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "ReleaseManifest":
        required = [
            "schema_version",
            "channel",
            "package_name",
            "version",
            "python_requires",
            "installer_min_version",
        ]
        missing = [key for key in required if not isinstance(payload.get(key), str) or not str(payload.get(key)).strip()]
        if missing:
            raise ManifestError(f"Manifest missing required string fields: {', '.join(missing)}")
        release_notes_url = payload.get("release_notes_url")
        source_url = payload.get("source_url")
        if release_notes_url is not None and not isinstance(release_notes_url, str):
            raise ManifestError("Manifest field release_notes_url must be a string when provided")
        if source_url is not None and not isinstance(source_url, str):
            raise ManifestError("Manifest field source_url must be a string when provided")
        return cls(
            schema_version=str(payload["schema_version"]),
            channel=str(payload["channel"]),
            package_name=str(payload["package_name"]),
            version=str(payload["version"]),
            python_requires=str(payload["python_requires"]),
            installer_min_version=str(payload["installer_min_version"]),
            release_notes_url=release_notes_url,
            source_url=source_url,
        )


class ManifestFetcher:
    def fetch(self, manifest_url: str) -> ReleaseManifest:
        payload = self.fetch_payload(manifest_url)
        return ReleaseManifest.from_mapping(payload)

    def fetch_payload(self, manifest_url: str) -> dict[str, object]:
        parsed = urlparse(manifest_url)
        try:
            if parsed.scheme in {"", "file"}:
                path = Path(parsed.path if parsed.scheme == "file" else manifest_url)
                return json.loads(path.read_text(encoding="utf-8"))
            with urlopen(manifest_url, timeout=5.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except ManifestError:
            raise
        except json.JSONDecodeError as error:
            raise ManifestError(f"Manifest is not valid JSON: {error}") from error
        except OSError as error:
            raise ManifestNetworkError(str(error)) from error
