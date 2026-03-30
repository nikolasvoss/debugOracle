from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from ....artifacts.models import (
    SessionEvent,
    StackFrame,
    VariableEntry,
    VariableEvidence,
    VARIABLE_BUCKET_LOCALS,
    VARIABLE_BUCKET_UNKNOWN,
    VARIABLE_BUCKET_WATCHPOINTS,
)
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
    variable_evidence: VariableEvidence
    events: list[SessionEvent]
    parse_warnings: list[str]
    mi_record_count: int
    non_mi_line_count: int
    mi_parse_error_count: int
    parse_event_counts: dict[str, int]
    parse_event_severity_counts: dict[str, int]
    noise_line_counts: dict[str, int]
    noise_pattern_counts: Counter[str]


def parse_gdb_transcript(
    gdb_text: str, *, now_text: Callable[[], str]
) -> GdbTranscriptParseResult:
    latest_stop: dict[str, Any] | None = None
    latest_stack: list[StackFrame] = []
    latest_registers: dict[str, str] = {}
    variable_evidence = VariableEvidence()
    variable_order = 0
    events: list[SessionEvent] = []
    parse_warnings: list[str] = []
    mi_record_count = 0
    non_mi_line_count = 0
    mi_parse_error_count = 0
    noise_line_counts = Counter[str]()

    if not gdb_text:
        parse_warnings.append(
            "No GDB/MI input was provided before building this snapshot."
        )

    parse_event_counts = Counter[str]()
    parse_event_severity = Counter[str]()
    noise_pattern_counts = Counter[str]()
    for line_number, raw_line in enumerate(gdb_text.splitlines(), start=1):
        timestamp = now_text()
        stripped = raw_line.strip()

        if stripped == "(gdb)":
            _record_noise_event(
                kind="prompt-marker",
                raw=stripped,
                normalized=stripped,
                dedupe_key=stripped,
                pattern_key=stripped,
                line_number=line_number,
                timestamp=timestamp,
                parse_event_counts=parse_event_counts,
                parse_event_severity=parse_event_severity,
                noise_line_counts=noise_line_counts,
                noise_pattern_counts=noise_pattern_counts,
                events=events,
            )
            non_mi_line_count += 1
            continue

        if stripped.startswith('@"') or stripped.startswith('~"'):
            normalized = strip_console_output(stripped)
            _record_noise_event(
                kind="console-output",
                raw=stripped,
                normalized=normalized,
                dedupe_key=normalized,
                pattern_key=normalized[:64],
                line_number=line_number,
                timestamp=timestamp,
                parse_event_counts=parse_event_counts,
                parse_event_severity=parse_event_severity,
                noise_line_counts=noise_line_counts,
                noise_pattern_counts=noise_pattern_counts,
                events=events,
            )
            non_mi_line_count += 1
            continue

        try:
            record = parse_mi_record(raw_line)
        except MIParseError as error:
            mi_parse_error_count += 1
            _record_parse_error_event(
                raw_line=raw_line,
                error=error,
                line_number=line_number,
                timestamp=timestamp,
                parse_event_counts=parse_event_counts,
                parse_event_severity=parse_event_severity,
                events=events,
                parse_warnings=parse_warnings,
            )
            continue

        if record is None:
            if stripped:
                non_mi_line_count += 1
                _record_noise_event(
                    kind="non_mi_line",
                    raw=stripped,
                    normalized=stripped,
                    dedupe_key=stripped,
                    pattern_key=stripped[:64],
                    line_number=line_number,
                    timestamp=timestamp,
                    parse_event_counts=parse_event_counts,
                    parse_event_severity=parse_event_severity,
                    noise_line_counts=noise_line_counts,
                    noise_pattern_counts=noise_pattern_counts,
                    events=events,
                )
            continue

        mi_record_count += 1
        _record_mi_event(
            record=record,
            line_number=line_number,
            timestamp=timestamp,
            parse_event_counts=parse_event_counts,
            parse_event_severity=parse_event_severity,
            events=events,
        )
        latest_stop, latest_stack = _update_stop_context(
            record=record,
            latest_stop=latest_stop,
            latest_stack=latest_stack,
        )
        latest_stack, latest_registers, variable_order = _update_done_context(
            record=record,
            latest_stack=latest_stack,
            latest_registers=latest_registers,
            variable_evidence=variable_evidence,
            variable_order=variable_order,
        )

    if latest_stop:
        watchpoint_entries = extract_watchpoint_entries(
            latest_stop, start_order=variable_order
        )
        if watchpoint_entries:
            variable_evidence.watchpoints = watchpoint_entries

    return GdbTranscriptParseResult(
        latest_stop=latest_stop,
        latest_stack=latest_stack,
        latest_registers=latest_registers,
        variable_evidence=variable_evidence,
        events=events,
        parse_warnings=parse_warnings,
        mi_record_count=mi_record_count,
        non_mi_line_count=non_mi_line_count,
        mi_parse_error_count=mi_parse_error_count,
        parse_event_counts={
            key: int(value) for key, value in parse_event_counts.items()
        },
        parse_event_severity_counts={
            key: int(value) for key, value in parse_event_severity.items()
        },
        noise_line_counts={key: int(value) for key, value in noise_line_counts.items()},
        noise_pattern_counts=noise_pattern_counts,
    )


def _record_noise_event(
    *,
    kind: str,
    raw: str,
    normalized: str,
    dedupe_key: str,
    pattern_key: str,
    line_number: int,
    timestamp: str,
    parse_event_counts: Counter[str],
    parse_event_severity: Counter[str],
    noise_line_counts: Counter[str],
    noise_pattern_counts: Counter[str],
    events: list[SessionEvent],
) -> None:
    parse_event_counts[kind] += 1
    parse_event_severity["info"] += 1
    noise_line_counts[kind] += 1
    events.append(
        SessionEvent(
            source="gdb_mi",
            timestamp=timestamp,
            kind=kind,
            payload={
                "line": line_number,
                "raw": raw,
                "normalized": normalized,
                "dedupe_key": dedupe_key,
                "severity": "info",
            },
        )
    )
    noise_pattern_counts[pattern_key] += 1


def _record_parse_error_event(
    *,
    raw_line: str,
    error: MIParseError,
    line_number: int,
    timestamp: str,
    parse_event_counts: Counter[str],
    parse_event_severity: Counter[str],
    events: list[SessionEvent],
    parse_warnings: list[str],
) -> None:
    kind = (
        "mi-parse-error-known"
        if is_likely_mi_line(raw_line)
        else "mi-parse-error-unhandled"
    )
    parse_event_counts[kind] += 1
    parse_event_severity["warn"] += 1
    parse_warnings.append(f"Line {line_number}: unable to parse MI record: {error}")
    events.append(
        SessionEvent(
            source="gdb_mi",
            timestamp=timestamp,
            kind=kind,
            payload={
                "line": line_number,
                "raw": raw_line,
                "error": str(error),
                "severity": "warn",
            },
        )
    )


def _record_mi_event(
    *,
    record: Any,
    line_number: int,
    timestamp: str,
    parse_event_counts: Counter[str],
    parse_event_severity: Counter[str],
    events: list[SessionEvent],
) -> None:
    kind = f"{record.prefix}{record.kind}"
    parse_event_counts[kind] += 1
    parse_event_severity["info"] += 1
    events.append(
        SessionEvent(
            source="gdb_mi",
            timestamp=timestamp,
            kind=kind,
            payload={"line": line_number, "severity": "info", **record.data},
        )
    )


def _update_stop_context(
    *,
    record: Any,
    latest_stop: dict[str, Any] | None,
    latest_stack: list[StackFrame],
) -> tuple[dict[str, Any] | None, list[StackFrame]]:
    if record.prefix != "*" or record.kind != "stopped":
        return latest_stop, latest_stack
    latest_stop = dict(record.data)
    frame = record.data.get("frame")
    if isinstance(frame, dict):
        latest_stack = [normalize_frame(frame, default_level=0)]
    return latest_stop, latest_stack


def _update_done_context(
    *,
    record: Any,
    latest_stack: list[StackFrame],
    latest_registers: dict[str, str],
    variable_evidence: VariableEvidence,
    variable_order: int,
) -> tuple[list[StackFrame], dict[str, str], int]:
    if record.prefix != "^" or record.kind != "done":
        return latest_stack, latest_registers, variable_order
    data = record.data
    if "stack" in data:
        latest_stack = extract_stack(data["stack"])
    if "register-values" in data:
        latest_registers = extract_registers(data["register-values"])
    if "locals" in data:
        entries = extract_variable_entries(
            data["locals"],
            bucket=VARIABLE_BUCKET_LOCALS,
            origin="gdb-mi-locals",
            start_order=variable_order,
        )
        variable_evidence.locals.extend(entries)
        variable_order += len(entries)
    if "variables" in data:
        entries = extract_variable_entries(
            data["variables"],
            bucket=VARIABLE_BUCKET_UNKNOWN,
            origin="gdb-mi-variables",
            start_order=variable_order,
        )
        variable_evidence.unknown.extend(entries)
        variable_order += len(entries)
    return latest_stack, latest_registers, variable_order


def extract_stack(raw_stack: object) -> list[StackFrame]:
    frames: list[StackFrame] = []
    if isinstance(raw_stack, list):
        for item in raw_stack:
            if (
                isinstance(item, dict)
                and "frame" in item
                and isinstance(item["frame"], dict)
            ):
                frames.append(normalize_frame(item["frame"]))
            elif isinstance(item, dict):
                frames.append(normalize_frame(item))
    elif isinstance(raw_stack, dict):
        frames.append(normalize_frame(raw_stack))
    return sorted(
        frames, key=lambda frame: frame.level if frame.level is not None else 9999
    )


def normalize_frame(
    raw_frame: dict[str, Any], default_level: int | None = None
) -> StackFrame:
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


def extract_variable_entries(
    raw_values: object,
    *,
    bucket: str,
    origin: str,
    start_order: int,
) -> list[VariableEntry]:
    values: list[VariableEntry] = []
    if not isinstance(raw_values, list):
        return values
    for offset, item in enumerate(raw_values):
        if not isinstance(item, dict):
            continue
        name = as_text(item.get("name"))
        value = as_text(item.get("value"))
        if name is not None:
            values.append(
                VariableEntry(
                    name=name,
                    value=value or "<unavailable>",
                    bucket=bucket,
                    availability="captured"
                    if value is not None
                    else "value-unavailable",
                    origin=origin,
                    frame=as_text(item.get("arg"))
                    if bucket == VARIABLE_BUCKET_LOCALS
                    else None,
                    order=start_order + offset,
                )
            )
    return values


def extract_watchpoint_entries(
    latest_stop: dict[str, Any], *, start_order: int
) -> list[VariableEntry]:
    reason = as_text(latest_stop.get("reason")) or ""
    if "watchpoint" not in reason:
        return []
    watchpoint = latest_stop.get("wpt")
    if not isinstance(watchpoint, dict):
        return []
    name = (
        as_text(watchpoint.get("exp"))
        or as_text(watchpoint.get("number"))
        or "watchpoint"
    )
    value_payload = latest_stop.get("value")
    value = None
    availability = "value-unavailable"
    detail: dict[str, Any] = {}
    if isinstance(value_payload, dict):
        old = as_text(value_payload.get("old"))
        new = as_text(value_payload.get("new"))
        if old is not None:
            detail["old"] = old
        if new is not None:
            detail["new"] = new
            value = new
            availability = "captured"
    return [
        VariableEntry(
            name=name,
            value=value,
            bucket=VARIABLE_BUCKET_WATCHPOINTS,
            availability=availability,
            origin="gdb-mi-watchpoint-stop",
            order=start_order,
            detail=detail,
        )
    ]


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
    if not (line.startswith('@"') or line.startswith('~"')):
        return line
    start = 2
    if not line.endswith('"'):
        return line[start:]
    body = line[start:-1]
    chars: list[str] = []
    cursor = 0
    while cursor < len(body):
        char = body[cursor]
        if char == "\\" and cursor + 1 < len(body):
            cursor += 1
            escaped = body[cursor]
            chars.append(
                {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(
                    escaped, escaped
                )
            )
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
