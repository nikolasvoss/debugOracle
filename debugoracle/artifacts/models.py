from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, overload

CURRENT_BUNDLE_SCHEMA_VERSION = "5"

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
class GdbSource:
    raw_text: str | None = None
    events: list[SessionEvent] = field(default_factory=list)
    event_count: int = 0
    embedded: bool = False


@dataclass
class RttSource:
    raw_text: str | None = None
    lines: list[str] = field(default_factory=list)
    line_count: int = 0
    embedded: bool = False


@dataclass
class RegisterEntry:
    name: str
    address: str
    width_bits: int
    read_status: str
    value_hex: str | None = None
    failure_reason: str | None = None
    skip_reason: str | None = None
    access: str | None = None


@dataclass
class PeripheralRegisterSet:
    name: str
    base_address: str
    registers: list[RegisterEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RegisterSource:
    embedded: bool = False
    svd_source: str | None = None
    device_name: str | None = None
    peripheral_count: int = 0
    register_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    peripherals: list[PeripheralRegisterSet] = field(default_factory=list)


@dataclass
class MemoryReadEntry:
    status: str
    address: str
    size: int
    data_hex: str = ""
    failure_reason: str | None = None
    ascii_preview: str = ""


@dataclass
class MemorySource:
    embedded: bool = False
    entries: list[MemoryReadEntry] = field(default_factory=list)

    @property
    def requested_count(self) -> int:
        return len(self.entries)

    @property
    def success_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == "success")

    @property
    def failure_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == "failure")


@dataclass
class ArtifactSources:
    gdb: GdbSource = field(default_factory=GdbSource)
    rtt: RttSource = field(default_factory=RttSource)
    registers: RegisterSource = field(default_factory=RegisterSource)
    memory: MemorySource = field(default_factory=MemorySource)


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
    sources: ArtifactSources = field(default_factory=ArtifactSources)
    parse_warnings: list[str] = field(default_factory=list)
    live_state: dict[str, Any] = field(default_factory=dict)
    source_context: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def has_embedded_gdb_source(self) -> bool:
        return self.sources.gdb.embedded

    @property
    def has_embedded_rtt_source(self) -> bool:
        return self.sources.rtt.embedded

    @property
    def has_embedded_register_source(self) -> bool:
        return self.sources.registers.embedded

    @property
    def has_embedded_memory_source(self) -> bool:
        return self.sources.memory.embedded

    def require_embedded_gdb_source(self) -> GdbSource:
        if not self.has_embedded_gdb_source:
            raise RuntimeError(
                "embedded gdb source data is unavailable in this snapshot"
            )
        return self.sources.gdb

    def require_embedded_rtt_source(self) -> RttSource:
        if not self.has_embedded_rtt_source:
            raise RuntimeError(
                "embedded rtt source data is unavailable in this snapshot"
            )
        return self.sources.rtt

    def require_embedded_register_source(self) -> RegisterSource:
        if not self.has_embedded_register_source:
            raise RuntimeError(
                "embedded register source data is unavailable in this snapshot"
            )
        return self.sources.registers

    def require_embedded_memory_source(self) -> MemorySource:
        if not self.has_embedded_memory_source:
            raise RuntimeError(
                "embedded memory source data is unavailable in this snapshot"
            )
        return self.sources.memory

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InvestigationArtifact":
        if not isinstance(raw, dict):
            raise ValueError("snapshot payload must be a JSON object")
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
        variable_evidence = _parse_variable_evidence(raw)
        sources = _parse_sources(raw)
        return cls(
            snapshot_id=_as_optional_str(raw.get("snapshot_id"), "unknown"),
            captured_at=_as_optional_str(raw.get("captured_at"), ""),
            stop_reason=_as_optional_str(raw.get("stop_reason")),
            pc=_as_optional_str(raw.get("pc")),
            lr=_as_optional_str(raw.get("lr")),
            sp=_as_optional_str(raw.get("sp")),
            schema_version=_as_optional_str(
                raw.get("schema_version"), CURRENT_BUNDLE_SCHEMA_VERSION
            )
            or CURRENT_BUNDLE_SCHEMA_VERSION,
            frames=frames,
            registers=_as_str_dict(raw.get("registers")),
            variable_evidence=variable_evidence,
            sources=sources,
            parse_warnings=[
                _as_optional_str(item, "")
                for item in _as_list(raw.get("parse_warnings"), [])
                if item is not None
            ],
            live_state=_as_any_dict(raw.get("live_state")),
            source_context=_as_any_dict(raw.get("source_context")),
            provenance=_as_any_dict(raw.get("provenance")),
        )


@dataclass(frozen=True)
class EvidenceAnswer:
    """Structured answer to a debug question, synthesized from artifact evidence."""

    question: str
    conclusion: str
    confidence: str  # "high" | "medium" | "low" | "unknown"
    evidence_sources: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)


__all__ = [
    "ArtifactSources",
    "CURRENT_BUNDLE_SCHEMA_VERSION",
    "EvidenceAnswer",
    "GdbSource",
    "InvestigationArtifact",
    "MemoryReadEntry",
    "MemorySource",
    "PeripheralRegisterSet",
    "RegisterEntry",
    "RegisterSource",
    "RttSource",
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
            locals=_parse_variable_bucket(
                payload.get(VARIABLE_BUCKET_LOCALS), VARIABLE_BUCKET_LOCALS
            ),
            globals=_parse_variable_bucket(
                payload.get(VARIABLE_BUCKET_GLOBALS), VARIABLE_BUCKET_GLOBALS
            ),
            watchpoints=_parse_variable_bucket(
                payload.get(VARIABLE_BUCKET_WATCHPOINTS), VARIABLE_BUCKET_WATCHPOINTS
            ),
            unknown=_parse_variable_bucket(
                payload.get(VARIABLE_BUCKET_UNKNOWN), VARIABLE_BUCKET_UNKNOWN
            ),
        )
    return VariableEvidence()


def _parse_sources(raw: dict[str, Any]) -> ArtifactSources:
    payload = raw.get("sources")
    if not isinstance(payload, dict):
        raise ValueError("snapshot payload is missing the canonical 'sources' object")
    raw_gdb = payload.get("gdb")
    raw_rtt = payload.get("rtt")
    raw_registers = payload.get("registers")
    raw_memory = payload.get("memory")
    if not isinstance(raw_gdb, dict):
        raise ValueError(
            "snapshot payload is missing the canonical 'sources.gdb' object"
        )
    if not isinstance(raw_rtt, dict):
        raise ValueError(
            "snapshot payload is missing the canonical 'sources.rtt' object"
        )
    if not isinstance(raw_registers, dict):
        raise ValueError(
            "snapshot payload is missing the canonical 'sources.registers' object"
        )
    if not isinstance(raw_memory, dict):
        raise ValueError(
            "snapshot payload is missing the canonical 'sources.memory' object"
        )

    gdb_events = _parse_events(raw_gdb.get("events"))
    rtt_lines = [
        _as_optional_str(line, "")
        for line in _as_list(raw_rtt.get("lines"), [])
        if line is not None
    ]
    gdb_event_count = _to_int(raw_gdb.get("event_count"))
    rtt_line_count = _to_int(raw_rtt.get("line_count"))
    return ArtifactSources(
        gdb=GdbSource(
            raw_text=_as_optional_str(raw_gdb.get("raw_text")),
            events=gdb_events,
            event_count=(
                gdb_event_count if gdb_event_count is not None else len(gdb_events)
            ),
            embedded=bool(raw_gdb.get("embedded", False)),
        ),
        rtt=RttSource(
            raw_text=_as_optional_str(raw_rtt.get("raw_text")),
            lines=rtt_lines,
            line_count=(
                rtt_line_count if rtt_line_count is not None else len(rtt_lines)
            ),
            embedded=bool(raw_rtt.get("embedded", False)),
        ),
        registers=_parse_register_source(raw_registers),
        memory=_parse_memory_source(raw_memory),
    )


def _parse_register_source(value: object) -> RegisterSource:
    if not isinstance(value, dict):
        return RegisterSource(embedded=False)
    embedded = bool(value.get("embedded", False))
    if not embedded:
        return RegisterSource(embedded=False)
    peripherals: list[PeripheralRegisterSet] = []
    for raw_peripheral in _as_list(value.get("peripherals"), []):
        if not isinstance(raw_peripheral, dict):
            continue
        name = _as_optional_str(raw_peripheral.get("name"))
        base_address = _as_optional_str(raw_peripheral.get("base_address"))
        if name is None or base_address is None:
            continue
        registers: list[RegisterEntry] = []
        for raw_register in _as_list(raw_peripheral.get("registers"), []):
            if not isinstance(raw_register, dict):
                continue
            register_name = _as_optional_str(raw_register.get("name"))
            address = _as_optional_str(raw_register.get("address"))
            width_bits = _to_int(raw_register.get("width_bits"))
            read_status = _as_optional_str(raw_register.get("read_status"))
            if (
                register_name is None
                or address is None
                or width_bits is None
                or read_status is None
            ):
                continue
            registers.append(
                RegisterEntry(
                    name=register_name,
                    address=address,
                    width_bits=width_bits,
                    read_status=read_status,
                    value_hex=_as_optional_str(raw_register.get("value_hex")),
                    failure_reason=_as_optional_str(raw_register.get("failure_reason")),
                    skip_reason=_as_optional_str(raw_register.get("skip_reason")),
                    access=_as_optional_str(raw_register.get("access")),
                )
            )
        peripherals.append(
            PeripheralRegisterSet(
                name=name,
                base_address=base_address,
                registers=registers,
                warnings=[
                    _as_optional_str(warning, "")
                    for warning in _as_list(raw_peripheral.get("warnings"), [])
                    if warning is not None
                ],
            )
        )
    _peripheral_count = _to_int(value.get("peripheral_count"))
    _register_count = _to_int(value.get("register_count"))
    return RegisterSource(
        embedded=True,
        svd_source=_as_optional_str(value.get("svd_source")),
        device_name=_as_optional_str(value.get("device_name")),
        peripheral_count=_peripheral_count
        if _peripheral_count is not None
        else len(peripherals),
        register_count=_register_count
        if _register_count is not None
        else sum(len(item.registers) for item in peripherals),
        success_count=_to_int(value.get("success_count")) or 0,
        failure_count=_to_int(value.get("failure_count")) or 0,
        skipped_count=_to_int(value.get("skipped_count")) or 0,
        peripherals=peripherals,
    )


def _parse_memory_source(value: object) -> MemorySource:
    if not isinstance(value, dict):
        return MemorySource(embedded=False)
    embedded = bool(value.get("embedded", False))
    if not embedded:
        return MemorySource(embedded=False)
    entries: list[MemoryReadEntry] = []
    for raw_entry in _as_list(value.get("entries"), []):
        if not isinstance(raw_entry, dict):
            continue
        status = _as_optional_str(raw_entry.get("status"), "")
        if status not in {"success", "failure"}:
            status = "failure"
        entries.append(
            MemoryReadEntry(
                status=status,
                address=_as_optional_str(raw_entry.get("address"), ""),
                size=_to_int(raw_entry.get("size")) or 0,
                data_hex=_as_optional_str(raw_entry.get("data_hex"), ""),
                failure_reason=_as_optional_str(raw_entry.get("failure_reason")),
                ascii_preview=_as_optional_str(raw_entry.get("ascii_preview"), ""),
            )
        )
    return MemorySource(embedded=True, entries=entries)


def _parse_events(value: object) -> list[SessionEvent]:
    events = []
    for raw_event in _as_list(value, []):
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
    return events


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
        order = _to_int(item.get("order"))
        entries.append(
            VariableEntry(
                name=name,
                value=_as_optional_str(item.get("value")),
                bucket=_as_optional_str(item.get("bucket"), bucket) or bucket,
                availability=_as_optional_str(item.get("availability"), "captured")
                or "captured",
                origin=_as_optional_str(item.get("origin"), "") or "",
                frame=_as_optional_str(item.get("frame")),
                order=order if order is not None else index,
                detail=_as_any_dict(detail),
            )
        )
    return entries


@overload
def _as_optional_str(value: object, default: str) -> str: ...
@overload
def _as_optional_str(value: object, default: None = ...) -> str | None: ...


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
