from __future__ import annotations

import hashlib
from collections import Counter
import json
from io import TextIOBase
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mi import MIParseError, parse_mi_record
from .models import CURRENT_BUNDLE_SCHEMA_VERSION, EvidenceBundle, SessionEvent, StackFrame

DEFAULT_RTT_WINDOW = 40
FULL_RTT_WINDOW = 200
RAW_GDB_MI_FILENAME = "raw-gdb-mi.log"
RAW_RTT_FILENAME = "raw-rtt.log"
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = {CURRENT_BUNDLE_SCHEMA_VERSION}

DEFAULT_SOURCE_CONTEXT: dict[str, object] = {}


class SnapshotLoadError(RuntimeError):
    """Raised when a snapshot cannot be loaded with strict integrity checks."""


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

    latest_stop: dict[str, Any] | None = None
    latest_stack: list[StackFrame] = []
    latest_registers: dict[str, str] = {}
    latest_watched: dict[str, str] = {}
    session_events: list[SessionEvent] = []
    parse_warnings: list[str] = []
    mi_record_count = 0
    non_mi_line_count = 0
    mi_parse_error_count = 0
    noise_line_counts = Counter[str]()

    if not gdb_text:
        parse_warnings.append("No GDB/MI input was provided before building this snapshot.")

    parse_event_counts = Counter[str]()
    parse_event_severity = Counter[str]()
    noise_pattern_counts = Counter[str]()
    for line_number, raw_line in enumerate(gdb_text.splitlines(), start=1):
        timestamp = utc_now()
        stripped = raw_line.strip()
        if stripped.startswith("(gdb)") and stripped == "(gdb)":
            parse_event_counts["prompt-marker"] += 1
            parse_event_severity["info"] += 1
            non_mi_line_count += 1
            noise_line_counts["prompt-marker"] += 1
            session_events.append(
                SessionEvent(
                    source="gdb_mi",
                    timestamp=timestamp,
                    kind="prompt-marker",
                    payload={
                        "line": line_number,
                        "raw": stripped,
                        "normalized": stripped,
                        "dedupe_key": stripped,
                        "severity": "info",
                    },
                )
            )
            noise_pattern_counts[stripped] += 1
            continue

        if stripped.startswith("@\"") or stripped.startswith("~\""):
            parse_event_counts["console-output"] += 1
            parse_event_severity["info"] += 1
            non_mi_line_count += 1
            normalized = _strip_console_output(stripped)
            noise_line_counts["console-output"] += 1
            session_events.append(
                SessionEvent(
                    source="gdb_mi",
                    timestamp=timestamp,
                    kind="console-output",
                    payload={
                        "line": line_number,
                        "raw": stripped,
                        "normalized": normalized,
                        "dedupe_key": normalized,
                        "severity": "info",
                    },
                )
            )
            noise_pattern_counts[normalized[:64]] += 1
            continue

        try:
            record = parse_mi_record(raw_line)
        except MIParseError as error:
            mi_parse_error_count += 1
            kind = "mi-parse-error-unhandled"
            severity = "warn"
            if _is_likely_mi_line(raw_line):
                kind = "mi-parse-error-known"
            parse_event_counts[kind] += 1
            parse_event_severity[severity] += 1
            parse_warnings.append(
                f"Line {line_number}: unable to parse MI record: {error}"
            )
            session_events.append(
                SessionEvent(
                    source="gdb_mi",
                    timestamp=timestamp,
                    kind=kind,
                    payload={
                        "line": line_number,
                        "raw": raw_line,
                        "error": str(error),
                        "severity": severity,
                    },
                )
            )
            continue

        if record is None:
            if stripped:
                parse_event_counts["non_mi_line"] += 1
                parse_event_severity["info"] += 1
                non_mi_line_count += 1
                noise_line_counts["non_mi_line"] += 1
                session_events.append(
                    SessionEvent(
                        source="gdb_mi",
                        timestamp=timestamp,
                        kind="non_mi_line",
                        payload={
                            "line": line_number,
                            "raw": stripped,
                            "normalized": stripped,
                            "dedupe_key": stripped,
                            "severity": "info",
                        },
                    )
                )
                noise_pattern_counts[stripped[:64]] += 1
            continue

        mi_record_count += 1
        parse_event_counts[f"{record.prefix}{record.kind}"] += 1
        parse_event_severity["info"] += 1
        event = SessionEvent(
            source="gdb_mi",
            timestamp=timestamp,
            kind=f"{record.prefix}{record.kind}",
            payload={"line": line_number, "severity": "info", **record.data},
        )
        session_events.append(event)

        if record.prefix == "*" and record.kind == "stopped":
            latest_stop = dict(record.data)
            frame = record.data.get("frame")
            if isinstance(frame, dict):
                latest_stack = [_normalize_frame(frame, default_level=0)]

        if record.prefix == "^" and record.kind == "done":
            if "stack" in record.data:
                latest_stack = _extract_stack(record.data["stack"])
            if "register-values" in record.data:
                latest_registers = _extract_registers(record.data["register-values"])
            if "locals" in record.data:
                latest_watched.update(_extract_named_values(record.data["locals"]))
            if "variables" in record.data:
                latest_watched.update(_extract_named_values(record.data["variables"]))

    stop_reason = _as_text(latest_stop.get("reason")) if latest_stop else None
    pc = _extract_pc(latest_stop, latest_registers, latest_stack)
    lr = latest_registers.get("14")
    sp = latest_registers.get("13")
    recent_rtt = _select_recent_rtt(rtt_text, rtt_window)
    snapshot_id = _make_snapshot_id(gdb_text, rtt_text, captured_at)

    if not latest_stack and latest_stop:
        frame = latest_stop.get("frame")
        if isinstance(frame, dict):
            latest_stack = [_normalize_frame(frame, default_level=0)]

    if not recent_rtt:
        parse_warnings.append("No RTT lines were available for this snapshot.")
        parse_event_counts["missing-rtt"] += 1
        parse_event_severity["warn"] += 1

    if non_mi_line_count:
        parse_warnings.append(
            "Transcript noise retained as context: "
            f"{noise_line_counts.get('prompt-marker', 0)} prompt markers, "
            f"{noise_line_counts.get('console-output', 0)} console-output lines, "
            f"{noise_line_counts.get('non_mi_line', 0)} other non-MI lines. "
            "Raw sidecar export provides the full transcript."
        )

    critical_events: list[str] = []
    if not gdb_text:
        critical_events.append("No GDB/MI input was provided before building this snapshot.")
        parse_event_counts["critical-missing-input"] += 1
        parse_event_severity["warn"] += 1
    if latest_stop is None:
        critical_events.append("Could not recover a stop context from the transcript.")
    critical_warning_count = len(critical_events)
    quality_score = _compute_evidence_quality_score(
        latest_stop=latest_stop,
        latest_stack=latest_stack,
        latest_registers=latest_registers,
        latest_watched=latest_watched,
        parse_error_count=mi_parse_error_count,
        warning_count=len(parse_warnings),
    )

    non_mi_top_patterns = [
        {"pattern": _normalize_non_mi_pattern_key(pattern), "count": int(count)}
        for pattern, count in noise_pattern_counts.most_common(8)
    ]
    known_event_counts = {key: int(value) for key, value in parse_event_counts.items()}
    severity_counts = {key: int(value) for key, value in parse_event_severity.items()}

    raw_export: dict[str, Any] = {}
    if export_dir is not None:
        should_export = export_raw or bool(non_mi_line_count or mi_parse_error_count or not gdb_text)
        raw_export["raw_exported"] = should_export
        if should_export:
            raw_export.update(
                _export_raw_inputs(
                    gdb_text=gdb_text,
                    rtt_text=rtt_text,
                    export_dir=Path(export_dir),
                )
            )

    return EvidenceBundle(
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        stop_reason=stop_reason,
        pc=pc,
        lr=lr,
        sp=sp,
        schema_version=CURRENT_BUNDLE_SCHEMA_VERSION,
        frames=latest_stack,
        registers=latest_registers,
        watched_values=latest_watched,
        recent_rtt=recent_rtt,
        source_context=dict(DEFAULT_SOURCE_CONTEXT),
        provenance={
            "gdb_mi_source": gdb_source,
            "rtt_source": rtt_source,
            "gdb_event_count": len(session_events),
            "rtt_line_count": len(recent_rtt),
            "rtt_total_line_count": len([line for line in rtt_text.splitlines()]),
            "rtt_window": rtt_window,
            "parse_warning_count": len(parse_warnings),
            "mi_record_count": mi_record_count,
            "non_mi_line_count": non_mi_line_count,
            "mi_parse_error_count": mi_parse_error_count,
            "evidence_quality_score": quality_score,
            "parse_event_counts": known_event_counts,
            "parse_event_severity_counts": severity_counts,
            "critical_warnings": critical_events,
            "critical_warning_count": critical_warning_count,
            "non_mi_pattern_counts": non_mi_top_patterns,
            "raw_line_warning_count": non_mi_line_count,
            **raw_export,
        },
        session_events=session_events,
        parse_warnings=parse_warnings,
    )


def load_bundle(path: str, *, strict: bool = False) -> EvidenceBundle:
    try:
        raw_text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        message = f"Could not read snapshot file '{path}': {error}"
        if strict:
            raise SnapshotLoadError(message) from error
        return _empty_bundle_from_load_error(path, f"Could not read snapshot file: {error}")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as error:
        message = f"Could not parse snapshot JSON in '{path}': {error}"
        if strict:
            raise SnapshotLoadError(message) from error
        return _empty_bundle_from_load_error(path, f"Could not parse snapshot JSON: {error}")
    bundle = EvidenceBundle.from_dict(raw)
    return _apply_schema_compatibility(
        bundle,
        raw=raw,
        path=path,
        strict=strict,
    )


def _empty_bundle_from_load_error(path: str, message: str) -> EvidenceBundle:
    return EvidenceBundle(
        snapshot_id="invalid-snapshot",
        captured_at=utc_now(),
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


def save_bundle(bundle: EvidenceBundle, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not bundle.schema_version:
        bundle.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
    target.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")


def _apply_schema_compatibility(
    bundle: EvidenceBundle,
    *,
    raw: object,
    path: str,
    strict: bool,
) -> EvidenceBundle:
    if not isinstance(raw, dict):
        bundle.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
        return bundle

    raw_version = raw.get("schema_version")
    if raw_version is None:
        bundle.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
        return bundle

    schema_version = str(raw_version).strip() or CURRENT_BUNDLE_SCHEMA_VERSION
    bundle.schema_version = schema_version
    if schema_version in SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        return bundle

    message = (
        f"Snapshot schema version '{schema_version}' in '{path}' is not supported; "
        "continuing with best-effort compatibility mode."
    )
    if strict:
        raise SnapshotLoadError(message)
    if message not in bundle.parse_warnings:
        bundle.parse_warnings.append(message)
        bundle.provenance["parse_warning_count"] = len(bundle.parse_warnings)
    return bundle


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
