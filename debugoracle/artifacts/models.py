from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CURRENT_BUNDLE_SCHEMA_VERSION = "2"

VARIABLE_BUCKET_LOCALS = "locals"
VARIABLE_BUCKET_GLOBALS = "globals"
VARIABLE_BUCKET_WATCHPOINTS = "watchpoints"
VARIABLE_BUCKET_UNKNOWN = "unknown"
VARIABLE_BUCKETS = (
    VARIABLE_BUCKET_LOCALS,
    VARIABLE_BUCKET_GLOBALS,
    VARIABLE_BUCKET_WATCHPOINTS,
    VARIABLE_BUCKET_UNKNOWN,
)


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
class VariableEntry:
    name: str
    value: str | None = None
    bucket: str = VARIABLE_BUCKET_UNKNOWN
    availability: str = "captured"
    origin: str = ""
    frame: str | None = None
    order: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class VariableEvidence:
    locals: list[VariableEntry] = field(default_factory=list)
    globals: list[VariableEntry] = field(default_factory=list)
    watchpoints: list[VariableEntry] = field(default_factory=list)
    unknown: list[VariableEntry] = field(default_factory=list)

    def bucket(self, name: str) -> list[VariableEntry]:
        return getattr(self, name, [])

    def all_entries(self) -> list[VariableEntry]:
        entries: list[VariableEntry] = []
        for bucket_name in VARIABLE_BUCKETS:
            entries.extend(self.bucket(bucket_name))
        return entries

    def count(self) -> int:
        return len(self.all_entries())


@dataclass
class InvestigationArtifact:
    snapshot_id: str
    captured_at: str
    stop_reason: str | None
    pc: str | None
    lr: str | None
    sp: str | None
    schema_version: str = CURRENT_BUNDLE_SCHEMA_VERSION
    frames: list[StackFrame] = field(default_factory=list)
    registers: dict[str, str] = field(default_factory=dict)
    variable_evidence: VariableEvidence = field(default_factory=VariableEvidence)
    recent_rtt: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    live_state: dict[str, Any] = field(default_factory=dict)
    source_context: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    session_events: list[SessionEvent] = field(default_factory=list)

    @property
    def watched_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for entry in self.variable_evidence.all_entries():
            if entry.value is not None:
                values[entry.name] = entry.value
        return values

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InvestigationArtifact":
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
        variable_evidence = _parse_variable_evidence(raw)
        return cls(
            snapshot_id=_as_optional_str(raw.get("snapshot_id"), "unknown"),
            captured_at=_as_optional_str(raw.get("captured_at"), ""),
            stop_reason=_as_optional_str(raw.get("stop_reason")),
            pc=_as_optional_str(raw.get("pc")),
            lr=_as_optional_str(raw.get("lr")),
            sp=_as_optional_str(raw.get("sp")),
            schema_version=_as_optional_str(raw.get("schema_version"), CURRENT_BUNDLE_SCHEMA_VERSION)
            or CURRENT_BUNDLE_SCHEMA_VERSION,
            frames=frames,
            registers=_as_str_dict(raw.get("registers")),
            variable_evidence=variable_evidence,
            recent_rtt=[_as_optional_str(line, "") for line in _as_list(raw.get("recent_rtt"), []) if line is not None],
            parse_warnings=[_as_optional_str(item, "") for item in _as_list(raw.get("parse_warnings"), []) if item is not None],
            live_state=_as_any_dict(raw.get("live_state")),
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
    var_scope: str = "all"
    var_names: list[str] = field(default_factory=list)
    var_detail: str = "compact"


@dataclass
class PromptPackage:
    goal: str
    intent: str | None
    summary: str
    evidence_appendix: str
    unknowns_and_gaps: list[str]
    instructions: str
    citations: list[str]


EvidenceBundle = InvestigationArtifact

__all__ = [
    "CURRENT_BUNDLE_SCHEMA_VERSION",
    "EvidenceBundle",
    "InvestigationArtifact",
    "InvestigationRequest",
    "PromptPackage",
    "SessionEvent",
    "StackFrame",
    "VariableEntry",
    "VariableEvidence",
    "VARIABLE_BUCKET_GLOBALS",
    "VARIABLE_BUCKET_LOCALS",
    "VARIABLE_BUCKET_UNKNOWN",
    "VARIABLE_BUCKET_WATCHPOINTS",
    "VARIABLE_BUCKETS",
]


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


def _parse_variable_evidence(raw: dict[str, Any]) -> VariableEvidence:
    payload = raw.get("variable_evidence")
    if isinstance(payload, dict):
        return VariableEvidence(
            locals=_parse_variable_bucket(payload.get(VARIABLE_BUCKET_LOCALS), VARIABLE_BUCKET_LOCALS),
            globals=_parse_variable_bucket(payload.get(VARIABLE_BUCKET_GLOBALS), VARIABLE_BUCKET_GLOBALS),
            watchpoints=_parse_variable_bucket(payload.get(VARIABLE_BUCKET_WATCHPOINTS), VARIABLE_BUCKET_WATCHPOINTS),
            unknown=_parse_variable_bucket(payload.get(VARIABLE_BUCKET_UNKNOWN), VARIABLE_BUCKET_UNKNOWN),
        )

    legacy = _as_str_dict(raw.get("watched_values"))
    if not legacy:
        return VariableEvidence()
    return VariableEvidence(
        unknown=[
            VariableEntry(
                name=name,
                value=value,
                bucket=VARIABLE_BUCKET_UNKNOWN,
                availability="captured",
                origin="legacy-watched-values",
                order=index,
            )
            for index, (name, value) in enumerate(legacy.items())
        ]
    )


def _parse_variable_bucket(value: object, bucket: str) -> list[VariableEntry]:
    entries: list[VariableEntry] = []
    for index, item in enumerate(_as_list(value, [])):
        if not isinstance(item, dict):
            continue
        detail = item.get("detail")
        if not isinstance(detail, dict):
            detail = {}
        name = _as_optional_str(item.get("name"))
        if name is None:
            continue
        entries.append(
            VariableEntry(
                name=name,
                value=_as_optional_str(item.get("value")),
                bucket=_as_optional_str(item.get("bucket"), bucket) or bucket,
                availability=_as_optional_str(item.get("availability"), "captured") or "captured",
                origin=_as_optional_str(item.get("origin"), "") or "",
                frame=_as_optional_str(item.get("frame")),
                order=_to_int(item.get("order")) if _to_int(item.get("order")) is not None else index,
                detail=_as_any_dict(detail),
            )
        )
    return entries


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
