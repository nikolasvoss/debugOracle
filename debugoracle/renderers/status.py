from __future__ import annotations

import json


def render_session_status(status, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(status.to_dict(), indent=2) + "\n"

    trust = getattr(status, "trust", {}) or {}
    readiness = getattr(status, "readiness", None)
    lines = [
        "DebugOracle Session Status",
        "",
        "Current State:",
        f"- Health: {status.health}",
        f"- Trust: {str(trust.get('verdict', 'unknown')).upper()}",
        f"- Trust Summary: {trust.get('summary', 'unavailable')}",
    ]
    if readiness is not None:
        lines.extend(
            [
                f"- Golden Path: {readiness.state}",
                f"- Golden Path Reason: {readiness.reason}",
                f"- Next Human Action: {readiness.next_human_action}",
            ]
        )
    lines.extend(
        [
            f"- Action: {status.action_state}",
            f"- Reason: {status.action_reason}",
            f"- Snapshot: {_snapshot_summary(status)}",
            f"- Snapshot ID: {status.snapshot_id or 'unavailable'}",
            f"- Snapshot Parse Warnings: {status.parse_warning_count}",
            "",
            "Evidence Availability:",
            _artifact_summary_line("Snapshot", status.snapshot),
            _artifact_summary_line("GDB/MI", status.gdb_mi),
            _artifact_summary_line("RTT", status.rtt),
            _rtt_capture_summary_line(status.rtt_capture),
        ]
    )
    if readiness is not None:
        lines.extend(["", "Golden Path Signals:"])
        lines.extend(_bullet_lines(readiness.signals or ["None"]))
    lines.extend(
        [
            "",
            "Trust Reasons:",
            *_bullet_lines(list(trust.get("reasons", [])) or ["None"]),
            "",
            "Next Useful Command:",
            f"- {status.recommended_next_command}",
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
    )
    lines.extend(_bullet_lines(status.warnings or ["None"]))
    if status.parse_warnings:
        lines.extend(["", "Snapshot Parse Warnings Detail:"])
        lines.extend(_bullet_lines(status.parse_warnings))
    return "\n".join(lines).rstrip() + "\n"


def _snapshot_summary(status) -> str:
    if not status.snapshot or not status.snapshot.exists:
        return "unavailable"
    freshness = "stale" if status.snapshot.stale else "fresh"
    snapshot_id = status.snapshot_id or "unavailable"
    return f"available ({snapshot_id}, {freshness})"


def _artifact_summary_line(label: str, artifact) -> str:
    if artifact is None or not artifact.exists:
        return f"- {label}: absent"
    freshness = "stale" if artifact.stale else "fresh"
    age = artifact.age_seconds if artifact.age_seconds is not None else "unavailable"
    return f"- {label}: present, {freshness}, age {age}s"


def _rtt_capture_summary_line(capture) -> str:
    if capture is None or not capture.exists:
        return "- RTT Capture: absent"
    freshness = "stale" if capture.stale else "fresh"
    status_text = capture.status or "no managed capture detected"
    bytes_captured = capture.bytes_captured if capture.bytes_captured is not None else "unavailable"
    return f"- RTT Capture: present, {freshness}, {status_text}, {bytes_captured} bytes"


def _artifact_lines(artifact) -> list[str]:
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


def _rtt_capture_lines(capture) -> list[str]:
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
        (f"- Transport Status: {capture.status}" if capture.status else "- Transport Status: no managed capture detected"),
        f"- Connected At: {capture.connected_at or 'unavailable'}",
        f"- Last Byte At: {capture.last_byte_at or 'unavailable'}",
        f"- Bytes Captured: {capture.bytes_captured if capture.bytes_captured is not None else 'unavailable'}",
        f"- Transport Error: {capture.error or 'none'}",
        f"- Parse Error: {capture.parse_error or 'none'}",
    ]


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]
