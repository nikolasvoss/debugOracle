from __future__ import annotations

import hashlib
import json
from io import TextIOBase
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .future import CapabilityRegistry, SourceContextProvider
from .mi import MIParseError, parse_mi_record
from .models import EvidenceBundle, SessionEvent, StackFrame

DEFAULT_RTT_WINDOW = 40
FULL_RTT_WINDOW = 200


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_bundle_from_files(
    gdb_mi_path: str,
    rtt_path: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
) -> EvidenceBundle:
    gdb_text = _read_text_file(gdb_mi_path, errors="replace", required=True)
    rtt_text = _read_text_file(rtt_path, errors="replace") if rtt_path else ""
    return build_bundle_from_text(
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_mi_path,
        rtt_source=rtt_path,
        rtt_window=rtt_window,
    )


def build_bundle_from_stream(
    stream: TextIOBase,
    rtt_text: str = "",
    gdb_source: str = "<stdin>",
    rtt_source: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
) -> EvidenceBundle:
    gdb_text = stream.read()
    return build_bundle_from_text(
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_source,
        rtt_source=rtt_source,
        rtt_window=rtt_window,
    )


def build_bundle_from_text(
    gdb_text: str,
    rtt_text: str = "",
    gdb_source: str = "<stdin>",
    rtt_source: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
) -> EvidenceBundle:
    captured_at = utc_now()
    registry = CapabilityRegistry()
    source_context_provider = SourceContextProvider()

    latest_stop: dict[str, Any] | None = None
    latest_stack: list[StackFrame] = []
    latest_registers: dict[str, str] = {}
    latest_watched: dict[str, str] = {}
    session_events: list[SessionEvent] = []
    parse_warnings: list[str] = []

    if not gdb_text:
        parse_warnings.append("No GDB/MI input was provided before building this snapshot.")

    for line_number, raw_line in enumerate(gdb_text.splitlines(), start=1):
        timestamp = utc_now()
        try:
            record = parse_mi_record(raw_line)
        except MIParseError as error:
            parse_warnings.append(
                f"Line {line_number}: unable to parse MI record: {error}"
            )
            session_events.append(
                SessionEvent(
                    source="gdb_mi",
                    timestamp=timestamp,
                    kind="parse_error",
                    payload={"line": line_number, "raw": raw_line, "error": str(error)},
                )
            )
            continue

        if record is None:
            stripped = raw_line.strip()
            if stripped:
                session_events.append(
                    SessionEvent(
                        source="gdb_mi",
                        timestamp=timestamp,
                        kind="non_mi_line",
                        payload={"line": line_number, "raw": stripped},
                    )
                )
                parse_warnings.append(
                    f"Line {line_number}: non-MI output retained as context"
                )
            continue

        event = SessionEvent(
            source="gdb_mi",
            timestamp=timestamp,
            kind=f"{record.prefix}{record.kind}",
            payload={"line": line_number, **record.data},
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

    return EvidenceBundle(
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        stop_reason=stop_reason,
        pc=pc,
        lr=lr,
        sp=sp,
        frames=latest_stack,
        registers=latest_registers,
        watched_values=latest_watched,
        recent_rtt=recent_rtt,
        source_context={
            **source_context_provider.enrich_placeholder(),
            "planned_capabilities": [
                capability.name for capability in registry.list_capabilities()
            ],
        },
        provenance={
            "gdb_mi_source": gdb_source,
            "rtt_source": rtt_source,
            "gdb_event_count": len(session_events),
            "rtt_line_count": len(recent_rtt),
            "rtt_total_line_count": len([line for line in rtt_text.splitlines()]),
            "rtt_window": rtt_window,
            "parse_warning_count": len(parse_warnings),
        },
        session_events=session_events,
        parse_warnings=parse_warnings,
    )


def load_bundle(path: str) -> EvidenceBundle:
    try:
        raw_text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return _empty_bundle_from_load_error(path, f"Could not read snapshot file: {error}")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as error:
        return _empty_bundle_from_load_error(path, f"Could not parse snapshot JSON: {error}")
    return EvidenceBundle.from_dict(raw)


def _empty_bundle_from_load_error(path: str, message: str) -> EvidenceBundle:
    return EvidenceBundle(
        snapshot_id="invalid-snapshot",
        captured_at=utc_now(),
        stop_reason=None,
        pc=None,
        lr=None,
        sp=None,
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
    target.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")


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
