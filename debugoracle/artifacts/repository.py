from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import CURRENT_BUNDLE_SCHEMA_VERSION, InvestigationArtifact

SUPPORTED_ARTIFACT_SCHEMA_VERSIONS = {"1", CURRENT_BUNDLE_SCHEMA_VERSION}


class ArtifactLoadError(RuntimeError):
    """Raised when an artifact cannot be loaded with strict integrity checks."""


def load_artifact(path: str, *, strict: bool = False) -> InvestigationArtifact:
    try:
        raw_text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        message = f"Could not read snapshot file '{path}': {error}"
        if strict:
            raise ArtifactLoadError(message) from error
        return _empty_artifact_from_load_error(path, f"Could not read snapshot file: {error}")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as error:
        message = f"Could not parse snapshot JSON in '{path}': {error}"
        if strict:
            raise ArtifactLoadError(message) from error
        return _empty_artifact_from_load_error(path, f"Could not parse snapshot JSON: {error}")
    artifact = InvestigationArtifact.from_dict(raw)
    return _apply_schema_compatibility(
        artifact,
        raw=raw,
        path=path,
        strict=strict,
    )


def save_artifact(artifact: InvestigationArtifact, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not artifact.schema_version:
        artifact.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
    target.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")


def _empty_artifact_from_load_error(path: str, message: str) -> InvestigationArtifact:
    return InvestigationArtifact(
        snapshot_id="invalid-snapshot",
        captured_at=_utc_now(),
        stop_reason=None,
        pc=None,
        lr=None,
        sp=None,
        schema_version=CURRENT_BUNDLE_SCHEMA_VERSION,
        parse_warnings=[message],
        provenance={
            "gdb_mi_source": path,
            "rtt_source": None,
            "gdb_event_count": 0,
            "rtt_line_count": 0,
            "rtt_total_line_count": 0,
            "rtt_window": 0,
            "parse_warning_count": 1,
        },
    )


def _apply_schema_compatibility(
    artifact: InvestigationArtifact,
    *,
    raw: object,
    path: str,
    strict: bool,
) -> InvestigationArtifact:
    if not isinstance(raw, dict):
        artifact.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
        return artifact

    raw_version = raw.get("schema_version")
    if raw_version is None:
        artifact.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
        return artifact

    schema_version = str(raw_version).strip() or CURRENT_BUNDLE_SCHEMA_VERSION
    artifact.schema_version = schema_version
    if schema_version in SUPPORTED_ARTIFACT_SCHEMA_VERSIONS:
        return artifact

    message = (
        f"Snapshot schema version '{schema_version}' in '{path}' is not supported; "
        "continuing with best-effort compatibility mode."
    )
    if strict:
        raise ArtifactLoadError(message)
    if message not in artifact.parse_warnings:
        artifact.parse_warnings.append(message)
        artifact.provenance["parse_warning_count"] = len(artifact.parse_warnings)
    return artifact


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
