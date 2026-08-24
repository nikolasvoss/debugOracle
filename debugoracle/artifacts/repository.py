from __future__ import annotations

import json
from pathlib import Path

from ..safe_io import atomic_write_text
from .models import CURRENT_BUNDLE_SCHEMA_VERSION, InvestigationArtifact

SUPPORTED_ARTIFACT_SCHEMA_VERSIONS = {CURRENT_BUNDLE_SCHEMA_VERSION}


class ArtifactLoadError(RuntimeError):
    """Raised when an artifact cannot be loaded with strict integrity checks."""


def load_artifact(path: str, *, strict: bool = False) -> InvestigationArtifact:
    _ = strict
    try:
        raw_text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ArtifactLoadError(
            f"Could not read snapshot file '{path}': {error}"
        ) from error
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ArtifactLoadError(
            f"Could not parse snapshot JSON in '{path}': {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ArtifactLoadError(f"Snapshot payload in '{path}' must be a JSON object.")
    schema_version = _resolve_schema_version(raw, path=path)
    try:
        artifact = InvestigationArtifact.from_dict(raw)
    except ValueError as error:
        raise ArtifactLoadError(
            f"Snapshot payload in '{path}' is not canonical: {error}"
        ) from error
    artifact.schema_version = schema_version
    return artifact


def save_artifact(
    artifact: InvestigationArtifact,
    path: str,
    *,
    workspace_root: str | Path | None = None,
) -> None:
    target = Path(path)
    payload = artifact.to_dict()
    if not artifact.schema_version:
        payload["schema_version"] = CURRENT_BUNDLE_SCHEMA_VERSION
    atomic_write_text(
        target,
        json.dumps(payload, indent=2),
        workspace_root=workspace_root,
    )


def _resolve_schema_version(raw: dict[str, object], *, path: str) -> str:
    raw_version = raw.get("schema_version")
    if raw_version is None:
        raise ArtifactLoadError(
            f"Snapshot payload in '{path}' is missing required 'schema_version'."
        )
    schema_version = str(raw_version).strip()
    if not schema_version:
        raise ArtifactLoadError(
            f"Snapshot payload in '{path}' has an empty schema version."
        )
    if schema_version not in SUPPORTED_ARTIFACT_SCHEMA_VERSIONS:
        raise ArtifactLoadError(
            f"Snapshot schema version '{schema_version}' in '{path}' is not supported."
        )
    return schema_version
