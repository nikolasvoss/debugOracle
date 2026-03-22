from __future__ import annotations

import json
from typing import Any
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .artifacts.repository import load_artifact
from .policy.halted_analysis import HaltPolicyDecision, evaluate_artifact_live_state
from .policy.trust import evaluate_artifact_trust
from .renderers.status import render_session_status
from .sources.streams.rtt import default_state_path as default_rtt_state_path
from .sources.streams.rtt import load_capture_state

DEFAULT_SESSION_DIR = ".dbgoracle"
DEFAULT_SNAPSHOT_FILENAME = "latest_snapshot.json"
DEFAULT_GDB_MI_FILENAME = "cortex-debug-shared-mi.log"
DEFAULT_RTT_FILENAME = "session.rtt"
DEFAULT_STALE_AFTER_SECONDS = 900


@dataclass(frozen=True)
class SessionConfig:
    workspace_root: Path
    snapshot_file: Path
    gdb_mi_file: Path
    rtt_file: Path
    rtt_state_file: Path
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS

    @classmethod
    def from_workspace(
        cls,
        workspace_root: str | Path = ".",
        snapshot_file: str | Path | None = None,
        gdb_mi_file: str | Path | None = None,
        rtt_file: str | Path | None = None,
        rtt_state_file: str | Path | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> "SessionConfig":
        root = Path(workspace_root).resolve()
        session_root = root / DEFAULT_SESSION_DIR
        snapshot_default = root / DEFAULT_SNAPSHOT_FILENAME
        gdb_mi_default = root / DEFAULT_GDB_MI_FILENAME
        rtt_default = root / DEFAULT_RTT_FILENAME
        rtt_session_default = session_root / DEFAULT_RTT_FILENAME
        rtt_path = _resolve_path(
            root,
            rtt_file,
            rtt_default,
            rtt_session_default,
        )
        return cls(
            workspace_root=root,
            snapshot_file=_resolve_path(
                root,
                snapshot_file,
                snapshot_default,
                session_root / DEFAULT_SNAPSHOT_FILENAME,
            ),
            gdb_mi_file=_resolve_path(
                root,
                gdb_mi_file,
                gdb_mi_default,
                session_root / DEFAULT_GDB_MI_FILENAME,
            ),
            rtt_file=rtt_path,
            rtt_state_file=_resolve_path(
                root,
                rtt_state_file,
                default_rtt_state_path(rtt_path),
            ),
            stale_after_seconds=stale_after_seconds,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: str(value) if isinstance(value, Path) else value for key, value in payload.items()}


@dataclass(frozen=True)
class ArtifactStatus:
    path: str
    exists: bool
    updated_at: str | None
    age_seconds: int | None
    stale: bool
    size_bytes: int | None


@dataclass(frozen=True)
class RttCaptureStatus:
    path: str
    exists: bool
    updated_at: str | None
    age_seconds: int | None
    stale: bool
    size_bytes: int | None
    source: str | None = None
    host: str | None = None
    port: int | None = None
    status: str | None = None
    connected_at: str | None = None
    last_byte_at: str | None = None
    bytes_captured: int | None = None
    error: str | None = None
    parse_error: str | None = None


@dataclass
class SessionStatus:
    checked_at: str
    workspace_root: str
    health: str
    snapshot_id: str | None
    parse_warning_count: int
    parse_warnings: list[str] = field(default_factory=list)
    trust: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    snapshot: ArtifactStatus | None = None
    gdb_mi: ArtifactStatus | None = None
    rtt: ArtifactStatus | None = None
    rtt_capture: RttCaptureStatus | None = None
    action_state: str = "evidence_missing"
    action_reason: str = "No DebugOracle artifacts were found in the session directory."
    recommended_next_command: str = "dbgoracle fetch --workspace-root ."

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def collect_session_status(
    config: SessionConfig,
    now: datetime | None = None,
) -> SessionStatus:
    checked_at_dt = _ensure_utc(now or datetime.now(timezone.utc))
    snapshot = _artifact_status(config.snapshot_file, checked_at_dt, config.stale_after_seconds)
    gdb_mi = _artifact_status(config.gdb_mi_file, checked_at_dt, config.stale_after_seconds)
    rtt = _artifact_status(config.rtt_file, checked_at_dt, config.stale_after_seconds)
    rtt_capture = _rtt_capture_status(
        config.rtt_state_file,
        checked_at_dt,
        config.stale_after_seconds,
    )

    health_issues: list[str] = []
    warnings: list[str] = []

    _track_artifact("Snapshot", snapshot, health_issues, missing_is_health_issue=True)
    _track_artifact("GDB/MI", gdb_mi, health_issues, missing_is_health_issue=True)
    _track_artifact("RTT", rtt, warnings, missing_is_health_issue=False)
    _track_rtt_capture(rtt, rtt_capture, warnings)

    snapshot_id: str | None = None
    parse_warnings: list[str] = []
    snapshot_usable = False
    halt_policy = HaltPolicyDecision(allowed=True, target_state="unspecified")
    variable_count: int | None = None
    has_embedded_gdb_source: bool | None = None
    critical_warnings: list[str] = []
    if snapshot.exists:
        bundle = load_artifact(snapshot.path)
        snapshot_id = bundle.snapshot_id
        parse_warnings = list(bundle.parse_warnings)
        halt_policy = evaluate_artifact_live_state(bundle.live_state)
        snapshot_usable = snapshot_id != "invalid-snapshot" and halt_policy.allowed
        variable_count = bundle.variable_evidence.count()
        has_embedded_gdb_source = bundle.has_embedded_gdb_source
        if not halt_policy.allowed:
            health_issues.extend(halt_policy.warnings)
        critical_warning_count = _as_int(bundle.provenance.get("critical_warning_count"))
        critical_warnings = _extract_critical_warnings(bundle, critical_warning_count)
        if critical_warnings:
            health_issues.extend(critical_warnings)
        for warning in parse_warnings:
            if _is_health_issue_warning(warning):
                health_issues.append(warning)
            else:
                warnings.append(warning)

    if not any((snapshot.exists, gdb_mi.exists, rtt.exists, rtt_capture.exists)):
        health_issues.append("No DebugOracle artifacts were found in the session directory.")

    health = "healthy" if not health_issues else "degraded"
    action_state, action_reason, recommended_next_command = _derive_action_guidance(
        snapshot=snapshot,
        snapshot_usable=snapshot_usable,
        gdb_mi=gdb_mi,
        rtt=rtt,
    )
    trust = evaluate_artifact_trust(
        snapshot_exists=snapshot.exists,
        snapshot_usable=snapshot_usable,
        snapshot_stale=snapshot.stale if snapshot is not None else False,
        action_state=action_state,
        action_reason=action_reason,
        recommended_next_command=recommended_next_command,
        halt_policy=halt_policy,
        critical_warnings=critical_warnings,
        parse_warnings=parse_warnings,
        variable_count=variable_count,
        has_embedded_gdb_source=has_embedded_gdb_source,
    ).to_dict()

    return SessionStatus(
        checked_at=checked_at_dt.replace(microsecond=0).isoformat(),
        workspace_root=str(config.workspace_root),
        health=health,
        snapshot_id=snapshot_id,
        parse_warning_count=len(parse_warnings),
        parse_warnings=parse_warnings,
        trust=trust,
        warnings=health_issues + warnings,
        snapshot=snapshot,
        gdb_mi=gdb_mi,
        rtt=rtt,
        rtt_capture=rtt_capture,
        action_state=action_state,
        action_reason=action_reason,
        recommended_next_command=recommended_next_command,
    )


def _artifact_status(path: Path, now: datetime, stale_after_seconds: int) -> ArtifactStatus:
    try:
        stat = path.stat()
    except OSError:
        return ArtifactStatus(
            path=str(path),
            exists=False,
            updated_at=None,
            age_seconds=None,
            stale=False,
            size_bytes=None,
        )

    updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age_seconds = max(0, int((now - updated_at).total_seconds()))
    stale = age_seconds > stale_after_seconds if stale_after_seconds >= 0 else False
    return ArtifactStatus(
        path=str(path),
        exists=True,
        updated_at=updated_at.replace(microsecond=0).isoformat(),
        age_seconds=age_seconds,
        stale=stale,
        size_bytes=stat.st_size,
    )


def _rtt_capture_status(
    path: Path,
    now: datetime,
    stale_after_seconds: int,
) -> RttCaptureStatus:
    artifact = _artifact_status(path, now, stale_after_seconds)
    if not artifact.exists:
        return RttCaptureStatus(
            path=artifact.path,
            exists=False,
            updated_at=artifact.updated_at,
            age_seconds=artifact.age_seconds,
            stale=artifact.stale,
            size_bytes=artifact.size_bytes,
        )

    try:
        capture = load_capture_state(path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return RttCaptureStatus(
            path=artifact.path,
            exists=True,
            updated_at=artifact.updated_at,
            age_seconds=artifact.age_seconds,
            stale=artifact.stale,
            size_bytes=artifact.size_bytes,
            parse_error=f"{error.__class__.__name__}: {error}",
        )

    return RttCaptureStatus(
        path=artifact.path,
        exists=True,
        updated_at=artifact.updated_at,
        age_seconds=artifact.age_seconds,
        stale=artifact.stale,
        size_bytes=artifact.size_bytes,
        source=capture.source,
        host=capture.host,
        port=capture.port,
        status=capture.status,
        connected_at=capture.connected_at,
        last_byte_at=capture.last_byte_at,
        bytes_captured=capture.bytes_captured,
        error=capture.error,
    )


def _track_artifact(
    label: str,
    artifact: ArtifactStatus,
    messages: list[str],
    *,
    missing_is_health_issue: bool,
) -> None:
    if not artifact.exists:
        messages.append(f"{label} file not found: {artifact.path}")
        return
    if artifact.stale:
        messages.append(f"{label} file is stale: {artifact.path} ({artifact.age_seconds}s old)")
    elif not missing_is_health_issue and artifact.age_seconds is not None and artifact.age_seconds > 0:
        return


def _artifact_lines(artifact: ArtifactStatus | None) -> list[str]:
    if artifact is None:
        return ["- None"]
    return [
        f"- Path: {artifact.path}",
        f"- Exists: {'yes' if artifact.exists else 'no'}",
        f"- Updated At: {artifact.updated_at or 'unavailable'}",
        f"- Age Seconds: {artifact.age_seconds if artifact.age_seconds is not None else 'unavailable'}",
        f"- Stale: {'yes' if artifact.stale else 'no'}",
        f"- Size Bytes: {artifact.size_bytes if artifact.size_bytes is not None else 'unavailable'}",
    ]


def _rtt_capture_lines(capture: RttCaptureStatus | None) -> list[str]:
    if capture is None:
        return ["- None"]
    return [
        f"- Path: {capture.path}",
        f"- Exists: {'yes' if capture.exists else 'no'}",
        f"- Updated At: {capture.updated_at or 'unavailable'}",
        f"- Age Seconds: {capture.age_seconds if capture.age_seconds is not None else 'unavailable'}",
        f"- Stale: {'yes' if capture.stale else 'no'}",
        f"- Size Bytes: {capture.size_bytes if capture.size_bytes is not None else 'unavailable'}",
        f"- Source: {capture.source or 'unavailable'}",
        f"- Host: {capture.host or 'unavailable'}",
        f"- Port: {capture.port if capture.port is not None else 'unavailable'}",
        (
            f"- Transport Status: {capture.status}"
            if capture.status
            else "- Transport Status: no managed capture detected"
        ),
        f"- Connected At: {capture.connected_at or 'unavailable'}",
        f"- Last Byte At: {capture.last_byte_at or 'unavailable'}",
        f"- Bytes Captured: {capture.bytes_captured if capture.bytes_captured is not None else 'unavailable'}",
        f"- Transport Error: {capture.error or 'none'}",
        f"- Parse Error: {capture.parse_error or 'none'}",
    ]


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _is_health_issue_warning(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "could not read snapshot file",
            "could not parse snapshot json",
            "evidence quality is reduced",
        )
    )


def _extract_critical_warnings(
    bundle: "Any",
    critical_warning_count: int | None,
) -> list[str]:
    if critical_warning_count is not None and critical_warning_count <= 0:
        return []
    raw = bundle.provenance.get("critical_warnings")
    if isinstance(raw, list):
        warnings = [item for item in raw if isinstance(item, str)]
        if warnings:
            return warnings
    if critical_warning_count is None:
        return []
    return ["Parser reported unresolved critical events while processing the snapshot."]


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _track_rtt_capture(
    rtt: ArtifactStatus,
    capture: RttCaptureStatus,
    warnings: list[str],
) -> None:
    if not capture.exists:
        return
    if capture.parse_error:
        warnings.append(
            f"Could not parse RTT capture state file: {capture.path} ({capture.parse_error})"
        )
        return
    if capture.stale:
        warnings.append(
            f"RTT capture state file is stale: {capture.path} ({capture.age_seconds}s old)"
        )
    if capture.error:
        warnings.append(f"RTT capture reported an error: {capture.error}")
    elif capture.status == "connected" and (capture.bytes_captured or 0) == 0:
        warnings.append("RTT capture connected but no bytes were captured yet.")
    elif capture.status == "idle":
        warnings.append("RTT capture is connected but currently idle.")
    elif capture.status == "waiting":
        warnings.append("RTT capture is waiting for the OpenOCD RTT TCP server.")
    if rtt.exists and rtt.size_bytes == 0 and (capture.bytes_captured or 0) == 0:
        warnings.append("RTT log file exists but is still empty.")


def _resolve_path(
    workspace_root: Path,
    override: str | Path | None,
    *default_paths: Path,
) -> Path:
    if override is None:
        for path in default_paths:
            if path.exists():
                return path
        if default_paths:
            return default_paths[0]
        raise ValueError("at least one default path is required")
    path = Path(override)
    if path.is_absolute():
        return path
    return workspace_root / path


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _derive_action_guidance(
    *,
    snapshot: ArtifactStatus,
    snapshot_usable: bool,
    gdb_mi: ArtifactStatus,
    rtt: ArtifactStatus,
) -> tuple[str, str, str]:
    raw_artifacts = [artifact for artifact in (gdb_mi, rtt) if artifact.exists]
    fresher_raw = [
        artifact
        for artifact in raw_artifacts
        if snapshot.exists
        and snapshot.updated_at is not None
        and artifact.updated_at is not None
        and artifact.updated_at > snapshot.updated_at
    ]
    if snapshot_usable and fresher_raw:
        return (
            "refresh_recommended",
            "Raw evidence is newer than the snapshot. Refresh the snapshot before relying on the current report.",
            "dbgoracle fetch --workspace-root .",
        )
    if snapshot_usable:
        return (
            "ready",
            "A reusable snapshot is available for inspection.",
            "dbgoracle report --workspace-root .",
        )
    if raw_artifacts:
        reason = (
            "Raw evidence is newer than the snapshot, but the existing snapshot is not usable for inspection."
            if snapshot.exists else
            "Raw evidence is available, but no usable snapshot has been built yet."
        )
        return (
            "capture_needed",
            reason,
            "dbgoracle fetch --workspace-root .",
        )
    return (
        "evidence_missing",
        "No snapshot or usable raw evidence is available in this workspace.",
        "dbgoracle fetch --workspace-root .",
    )
