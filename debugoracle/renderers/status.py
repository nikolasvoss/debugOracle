from __future__ import annotations

import json


def render_session_status(status, fmt: str = "text") -> str:
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
