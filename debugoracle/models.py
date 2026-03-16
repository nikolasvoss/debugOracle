from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SessionEvent:
    source: str = ""
    timestamp: str = ""
    kind: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class StackFrame:
    level: int | None = None
    addr: str | None = None
    func: str | None = None
    file: str | None = None
    fullname: str | None = None
    line: int | None = None


@dataclass
class EvidenceBundle:
    snapshot_id: str
    captured_at: str
    stop_reason: str | None
    pc: str | None
    lr: str | None
    sp: str | None
    frames: list[StackFrame] = field(default_factory=list)
    registers: dict[str, str] = field(default_factory=dict)
    watched_values: dict[str, str] = field(default_factory=dict)
    recent_rtt: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    source_context: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    session_events: list[SessionEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvidenceBundle":
        raw = raw or {}
        if not isinstance(raw, dict):
            raw = {}
        frames = []
        for raw_frame in _as_list(raw.get("frames"), []):
            if not isinstance(raw_frame, dict):
                continue
            frames.append(
                StackFrame(
                    level=_to_int(raw_frame.get("level")),
                    addr=_as_optional_str(raw_frame.get("addr")),
                    func=_as_optional_str(raw_frame.get("func")),
                    file=_as_optional_str(raw_frame.get("file")),
                    fullname=_as_optional_str(raw_frame.get("fullname")),
                    line=_to_int(raw_frame.get("line")),
                )
            )
        events = []
        for raw_event in _as_list(raw.get("session_events"), []):
            if not isinstance(raw_event, dict):
                continue
            payload = raw_event.get("payload")
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            events.append(
                SessionEvent(
                    source=_as_optional_str(raw_event.get("source"), ""),
                    timestamp=_as_optional_str(raw_event.get("timestamp"), ""),
                    kind=_as_optional_str(raw_event.get("kind"), ""),
                    payload=_as_str_dict(payload),
                )
            )
        return cls(
            snapshot_id=_as_optional_str(raw.get("snapshot_id"), "unknown"),
            captured_at=_as_optional_str(raw.get("captured_at"), ""),
            stop_reason=_as_optional_str(raw.get("stop_reason")),
            pc=_as_optional_str(raw.get("pc")),
            lr=_as_optional_str(raw.get("lr")),
            sp=_as_optional_str(raw.get("sp")),
            frames=frames,
            registers=_as_str_dict(raw.get("registers")),
            watched_values=_as_str_dict(raw.get("watched_values")),
            recent_rtt=[_as_optional_str(line, "") for line in _as_list(raw.get("recent_rtt"), []) if line is not None],
            parse_warnings=[_as_optional_str(item, "") for item in _as_list(raw.get("parse_warnings"), []) if item is not None],
            source_context=_as_any_dict(raw.get("source_context")),
            provenance=_as_any_dict(raw.get("provenance")),
            session_events=events,
        )


@dataclass
class InvestigationRequest:
    goal_text: str
    intent_text: str | None = None
    snapshot_ref: str | None = None
    format: str = "markdown"
    detail_level: str = "compact"


@dataclass
class PromptPackage:
    goal: str
    intent: str | None
    summary: str
    evidence_appendix: str
    unknowns_and_gaps: list[str]
    instructions: str
    citations: list[str]


def _as_list(value: object, default: list[Any] | None = None) -> list[Any]:
    if default is None:
        default = []
    if isinstance(value, list):
        return value
    return default


def _as_str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, str] = {}
    for key, item in value.items():
        key_text = _as_optional_str(key)
        if key_text is None:
            continue
        parsed[key_text] = _as_optional_str(item, "")
    return parsed


def _as_any_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, object] = {}
    for key, item in value.items():
        key_text = _as_optional_str(key)
        if key_text is None:
            continue
        parsed[key_text] = item
    return parsed


def _as_optional_str(value: object, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value)
    return text if text != "" else default


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value), 10)
    except ValueError:
        return None
