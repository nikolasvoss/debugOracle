from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .builder import load_bundle
from .rtt import default_state_path as default_rtt_state_path
from .rtt import load_capture_state

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
        rtt_path = _resolve_path(root, rtt_file, session_root / DEFAULT_RTT_FILENAME)
        return cls(
            workspace_root=root,
            snapshot_file=_resolve_path(root, snapshot_file, session_root / DEFAULT_SNAPSHOT_FILENAME),
            gdb_mi_file=_resolve_path(root, gdb_mi_file, session_root / DEFAULT_GDB_MI_FILENAME),
            rtt_file=rtt_path,
            rtt_state_file=_resolve_path(
                root,
                rtt_state_file,
                default_rtt_state_path(rtt_path),
            ),
            stale_after_seconds=max(0, stale_after_seconds),
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
    warnings: list[str] = field(default_factory=list)
    snapshot: ArtifactStatus | None = None
    gdb_mi: ArtifactStatus | None = None
    rtt: ArtifactStatus | None = None
    rtt_capture: RttCaptureStatus | None = None

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
    if snapshot.exists:
        bundle = load_bundle(snapshot.path)
        snapshot_id = bundle.snapshot_id
        parse_warnings = list(bundle.parse_warnings)
        for warning in parse_warnings:
            if _is_health_issue_warning(warning):
                health_issues.append(warning)
            else:
                warnings.append(warning)

    if not any((snapshot.exists, gdb_mi.exists, rtt.exists, rtt_capture.exists)):
        health_issues.append("No DebugOracle artifacts were found in the session directory.")

    health = "healthy" if not health_issues else "degraded"
    return SessionStatus(
        checked_at=checked_at_dt.replace(microsecond=0).isoformat(),
        workspace_root=str(config.workspace_root),
        health=health,
        snapshot_id=snapshot_id,
        parse_warning_count=len(parse_warnings),
        parse_warnings=parse_warnings,
        warnings=health_issues + warnings,
        snapshot=snapshot,
        gdb_mi=gdb_mi,
        rtt=rtt,
        rtt_capture=rtt_capture,
    )


def render_session_status(status: SessionStatus, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(status.to_dict(), indent=2) + "\n"

    lines = [
        "DebugOracle Session Status",
        "",
        f"- Checked At: {status.checked_at}",
        f"- Workspace Root: {status.workspace_root}",
        f"- Health: {status.health}",
        f"- Snapshot ID: {status.snapshot_id or 'unavailable'}",
        f"- Snapshot Parse Warnings: {status.parse_warning_count}",
        "",
        "Snapshot:",
        *_artifact_lines(status.snapshot),
        "",
        "GDB/MI:",
        *_artifact_lines(status.gdb_mi),
        "",
        "RTT:",
        *_artifact_lines(status.rtt),
        "",
        "RTT Capture:",
        *_rtt_capture_lines(status.rtt_capture),
        "",
        "Warnings:",
    ]
    lines.extend(_bullet_lines(status.warnings or ["None"]))
    if status.parse_warnings:
        lines.extend(["", "Snapshot Parse Warnings Detail:"])
        lines.extend(_bullet_lines(status.parse_warnings))
    return "\n".join(lines).rstrip() + "\n"


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
            "unable to parse mi record",
            "no gdb/mi input was provided",
        )
    )


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
    default_path: Path,
) -> Path:
    if override is None:
        return default_path
    path = Path(override)
    if path.is_absolute():
        return path
    return workspace_root / path


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
