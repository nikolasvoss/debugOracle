from __future__ import annotations

import hashlib
from collections import Counter
from io import TextIOBase
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts.bundle import SnapshotLoadError, load_bundle, save_bundle
from .artifacts.models import CURRENT_BUNDLE_SCHEMA_VERSION, EvidenceBundle, SessionEvent, StackFrame
from .pipeline.storage import build_artifact_from_sources
from .sources.debuggers.gdb.halt_snapshot import (
    GDB_HALT_SNAPSHOT_SOURCE,
    build_halt_snapshot,
)
from .sources.debuggers.gdb.transcript import (
    GDB_TRANSCRIPT_SOURCE,
    parse_gdb_transcript,
)

DEFAULT_RTT_WINDOW = 40
FULL_RTT_WINDOW = 200
RAW_GDB_MI_FILENAME = "raw-gdb-mi.log"
RAW_RTT_FILENAME = "raw-rtt.log"

DEFAULT_SOURCE_CONTEXT: dict[str, object] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_bundle_from_files(
    gdb_mi_path: str | None = None,
    rtt_path: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
    *,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
) -> EvidenceBundle:
    gdb_text = (
        _read_text_file(gdb_mi_path, errors="replace", required=True)
        if gdb_mi_path
        else ""
    )
    rtt_text = _read_text_file(rtt_path, errors="replace") if rtt_path else ""
    return build_bundle_from_text(
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_mi_path or "<missing-gdb-mi>",
        rtt_source=rtt_path,
        rtt_window=rtt_window,
        export_raw=export_raw,
        export_dir=export_dir,
    )


def build_bundle_from_stream(
    stream: TextIOBase,
    rtt_text: str = "",
    gdb_source: str = "<stdin>",
    rtt_source: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
    *,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
) -> EvidenceBundle:
    gdb_text = stream.read()
    return build_bundle_from_text(
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_source,
        rtt_source=rtt_source,
        rtt_window=rtt_window,
        export_raw=export_raw,
        export_dir=export_dir,
    )


def build_bundle_from_text(
    gdb_text: str,
    rtt_text: str = "",
    gdb_source: str = "<stdin>",
    rtt_source: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
    *,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
) -> EvidenceBundle:
    captured_at = utc_now()
    transcript = parse_gdb_transcript(gdb_text, now_text=utc_now)
    halt_snapshot = build_halt_snapshot(
        latest_stop=transcript.latest_stop,
        latest_stack=transcript.latest_stack,
        latest_registers=transcript.latest_registers,
        latest_watched=transcript.latest_watched,
    )
    artifact = build_artifact_from_sources(
        captured_at=captured_at,
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_source,
        rtt_source=rtt_source,
        transcript=transcript,
        halt_snapshot=halt_snapshot,
        rtt_window=rtt_window,
        export_raw=export_raw,
        export_dir=export_dir,
    )
    artifact.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
    artifact.source_context = dict(DEFAULT_SOURCE_CONTEXT)
    return artifact

def _export_raw_inputs(
    *,
    gdb_text: str,
    rtt_text: str,
    export_dir: Path,
) -> dict[str, Any]:
    export_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "raw_export_root": str(export_dir),
    }
    if gdb_text:
        gdb_path = export_dir / RAW_GDB_MI_FILENAME
        gdb_path.write_text(gdb_text, encoding="utf-8")
        payload["gdb_mi_raw_path"] = str(gdb_path)
        payload["gdb_mi_raw_bytes"] = gdb_path.stat().st_size
    if rtt_text:
        rtt_path = export_dir / RAW_RTT_FILENAME
        rtt_path.write_text(rtt_text, encoding="utf-8")
        payload["rtt_raw_path"] = str(rtt_path)
        payload["rtt_raw_bytes"] = rtt_path.stat().st_size
    return payload


def _extract_stack(raw_stack: object) -> list[StackFrame]:
    frames: list[StackFrame] = []
    if isinstance(raw_stack, list):
        for item in raw_stack:
            if isinstance(item, dict) and "frame" in item and isinstance(item["frame"], dict):
                frames.append(_normalize_frame(item["frame"]))
            elif isinstance(item, dict):
                frames.append(_normalize_frame(item))
    elif isinstance(raw_stack, dict):
        frames.append(_normalize_frame(raw_stack))
    return sorted(frames, key=lambda frame: frame.level if frame.level is not None else 9999)


def _normalize_frame(raw_frame: dict[str, Any], default_level: int | None = None) -> StackFrame:
    line = _to_int(raw_frame.get("line"))
    level = _to_int(raw_frame.get("level"))
    if level is None:
        level = default_level
    return StackFrame(
        level=level,
        addr=_as_text(raw_frame.get("addr")),
        func=_as_text(raw_frame.get("func")),
        file=_as_text(raw_frame.get("file")),
        fullname=_as_text(raw_frame.get("fullname")),
        line=line,
    )


def _extract_registers(raw_values: object) -> dict[str, str]:
    registers: dict[str, str] = {}
    if not isinstance(raw_values, list):
        return registers
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        number = _as_text(item.get("number"))
        value = _as_text(item.get("value"))
        if number is not None and value is not None:
            registers[number] = value
    return registers


def _extract_named_values(raw_values: object) -> dict[str, str]:
    values: dict[str, str] = {}
    if not isinstance(raw_values, list):
        return values
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        name = _as_text(item.get("name"))
        value = _as_text(item.get("value"))
        if name is not None:
            values[name] = value or "<unavailable>"
    return values


def _extract_pc(
    latest_stop: dict[str, Any] | None,
    registers: dict[str, str],
    frames: list[StackFrame],
) -> str | None:
    if latest_stop:
        frame = latest_stop.get("frame")
        if isinstance(frame, dict):
            addr = _as_text(frame.get("addr"))
            if addr:
                return addr
    if "15" in registers:
        return registers["15"]
    if frames and frames[0].addr:
        return frames[0].addr
    return None


def _select_recent_rtt(rtt_text: str, rtt_window: int) -> list[str]:
    lines = [line.rstrip() for line in rtt_text.splitlines() if line.strip()]
    if rtt_window <= 0:
        return []
    return lines[-rtt_window:] if len(lines) > rtt_window else lines


def _is_likely_mi_line(line: str) -> bool:
    cleaned = line.strip()
    cursor = 0
    while cursor < len(cleaned) and cleaned[cursor].isdigit():
        cursor += 1
    if cursor:
        cleaned = cleaned[cursor:].lstrip()
    return bool(cleaned) and cleaned[0] in {"^", "*", "=", "+"}


def _strip_console_output(line: str) -> str:
    if not (line.startswith("@\"") or line.startswith("~\"")):
        return line
    start = 2
    if not line.endswith("\""):
        return line[start:]
    body = line[start:-1]
    chars: list[str] = []
    cursor = 0
    while cursor < len(body):
        char = body[cursor]
        if char == "\\" and cursor + 1 < len(body):
            cursor += 1
            escaped = body[cursor]
            chars.append({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(escaped, escaped))
            cursor += 1
            continue
        chars.append(char)
        cursor += 1
    return "".join(chars)


def _normalize_non_mi_pattern_key(value: str) -> str:
    normalized = (
        value.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return " ".join(normalized.split()) or "<empty>"


def _compute_evidence_quality_score(
    latest_stop: dict[str, Any] | None,
    latest_stack: list[StackFrame],
    latest_registers: dict[str, str],
    latest_watched: dict[str, str],
    parse_error_count: int,
    warning_count: int,
) -> int:
    score = 100
    if latest_stop is None:
        score -= 30
    if not latest_stack:
        score -= 20
    if not latest_registers:
        score -= 20
    if not latest_watched:
        score -= 15
    score -= min(25, parse_error_count * 8)
    score -= min(5, warning_count // 4)
    return max(0, score)


def _read_text_file(path: str, errors: str = "strict", *, required: bool = False) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors=errors)
    except OSError as error:
        if required:
            raise
        return f"[DEBUGORACLE_READ_ERROR {path}: {error}]"


def _make_snapshot_id(gdb_text: str, rtt_text: str, captured_at: str) -> str:
    digest = hashlib.sha1(f"{captured_at}\n{gdb_text}\n{rtt_text}".encode("utf-8")).hexdigest()
    return f"snap-{digest[:12]}"


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value), 10)
    except ValueError:
        return None


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
