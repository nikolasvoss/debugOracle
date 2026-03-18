from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from ....artifacts.models import SessionEvent, StackFrame
from ....mi import MIParseError, parse_mi_record
from ...base import SourceDescriptor, validate_source_descriptor

GDB_TRANSCRIPT_SOURCE = validate_source_descriptor(
    SourceDescriptor(
        source_id="gdb_transcript",
        family="stream",
        trigger="passive",
        requires_halt=False,
        persistence_default="raw_sidecar",
        backend_dependency="gdb-mi",
        supports_parsing=True,
        supports_reduction=True,
    )
)


@dataclass
class GdbTranscriptParseResult:
    latest_stop: dict[str, Any] | None
    latest_stack: list[StackFrame]
    latest_registers: dict[str, str]
    latest_watched: dict[str, str]
    session_events: list[SessionEvent]
    parse_warnings: list[str]
    mi_record_count: int
    non_mi_line_count: int
    mi_parse_error_count: int
    parse_event_counts: dict[str, int]
    parse_event_severity_counts: dict[str, int]
    noise_line_counts: dict[str, int]
    noise_pattern_counts: Counter[str]


def parse_gdb_transcript(gdb_text: str, *, now_text: Callable[[], str]) -> GdbTranscriptParseResult:
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
        timestamp = now_text()
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
            normalized = strip_console_output(stripped)
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
            if is_likely_mi_line(raw_line):
                kind = "mi-parse-error-known"
            parse_event_counts[kind] += 1
            parse_event_severity[severity] += 1
            parse_warnings.append(f"Line {line_number}: unable to parse MI record: {error}")
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
        session_events.append(
            SessionEvent(
                source="gdb_mi",
                timestamp=timestamp,
                kind=f"{record.prefix}{record.kind}",
                payload={"line": line_number, "severity": "info", **record.data},
            )
        )

        if record.prefix == "*" and record.kind == "stopped":
            latest_stop = dict(record.data)
            frame = record.data.get("frame")
            if isinstance(frame, dict):
                latest_stack = [normalize_frame(frame, default_level=0)]

        if record.prefix == "^" and record.kind == "done":
            if "stack" in record.data:
                latest_stack = extract_stack(record.data["stack"])
            if "register-values" in record.data:
                latest_registers = extract_registers(record.data["register-values"])
            if "locals" in record.data:
                latest_watched.update(extract_named_values(record.data["locals"]))
            if "variables" in record.data:
                latest_watched.update(extract_named_values(record.data["variables"]))

    return GdbTranscriptParseResult(
        latest_stop=latest_stop,
        latest_stack=latest_stack,
        latest_registers=latest_registers,
        latest_watched=latest_watched,
        session_events=session_events,
        parse_warnings=parse_warnings,
        mi_record_count=mi_record_count,
        non_mi_line_count=non_mi_line_count,
        mi_parse_error_count=mi_parse_error_count,
        parse_event_counts={key: int(value) for key, value in parse_event_counts.items()},
        parse_event_severity_counts={key: int(value) for key, value in parse_event_severity.items()},
        noise_line_counts={key: int(value) for key, value in noise_line_counts.items()},
        noise_pattern_counts=noise_pattern_counts,
    )


def extract_stack(raw_stack: object) -> list[StackFrame]:
    frames: list[StackFrame] = []
    if isinstance(raw_stack, list):
        for item in raw_stack:
            if isinstance(item, dict) and "frame" in item and isinstance(item["frame"], dict):
                frames.append(normalize_frame(item["frame"]))
            elif isinstance(item, dict):
                frames.append(normalize_frame(item))
    elif isinstance(raw_stack, dict):
        frames.append(normalize_frame(raw_stack))
    return sorted(frames, key=lambda frame: frame.level if frame.level is not None else 9999)


def normalize_frame(raw_frame: dict[str, Any], default_level: int | None = None) -> StackFrame:
    line = to_int(raw_frame.get("line"))
    level = to_int(raw_frame.get("level"))
    if level is None:
        level = default_level
    return StackFrame(
        level=level,
        addr=as_text(raw_frame.get("addr")),
        func=as_text(raw_frame.get("func")),
        file=as_text(raw_frame.get("file")),
        fullname=as_text(raw_frame.get("fullname")),
        line=line,
    )


def extract_registers(raw_values: object) -> dict[str, str]:
    registers: dict[str, str] = {}
    if not isinstance(raw_values, list):
        return registers
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        number = as_text(item.get("number"))
        value = as_text(item.get("value"))
        if number is not None and value is not None:
            registers[number] = value
    return registers


def extract_named_values(raw_values: object) -> dict[str, str]:
    values: dict[str, str] = {}
    if not isinstance(raw_values, list):
        return values
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        name = as_text(item.get("name"))
        value = as_text(item.get("value"))
        if name is not None:
            values[name] = value or "<unavailable>"
    return values


def extract_pc(
    latest_stop: dict[str, Any] | None,
    registers: dict[str, str],
    frames: list[StackFrame],
) -> str | None:
    if latest_stop:
        frame = latest_stop.get("frame")
        if isinstance(frame, dict):
            addr = as_text(frame.get("addr"))
            if addr:
                return addr
    if "15" in registers:
        return registers["15"]
    if frames and frames[0].addr:
        return frames[0].addr
    return None


def is_likely_mi_line(line: str) -> bool:
    cleaned = line.strip()
    cursor = 0
    while cursor < len(cleaned) and cleaned[cursor].isdigit():
        cursor += 1
    if cursor:
        cleaned = cleaned[cursor:].lstrip()
    return bool(cleaned) and cleaned[0] in {"^", "*", "=", "+"}


def strip_console_output(line: str) -> str:
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


def to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value), 10)
    except ValueError:
        return None


def as_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
