from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..artifacts.models import EvidenceBundle, VariableEntry, VARIABLE_BUCKETS
from ._evidence_common import (
    mapping_section,
    parsing_summary_section,
    render_bullets,
    session_summary,
    stack_section,
    unknowns,
    variable_section,
    with_parse_warnings,
)


@dataclass
class ReportRenderOptions:
    variable_names: list[str] | None = None
    include_gdb: bool = False
    include_rtt: bool = False
    verbose: bool = False
    tail: int | None = None

    @property
    def include_variables(self) -> bool:
        return self.variable_names is not None or self.verbose

    @property
    def inspect_mode(self) -> bool:
        return self.include_variables or self.include_gdb or self.include_rtt or self.verbose


def render_report(
    bundle: EvidenceBundle,
    fmt: str = "text",
    *,
    options: ReportRenderOptions | None = None,
    variable_options=None,
) -> str:
    options = options or ReportRenderOptions()
    if options.inspect_mode:
        payload = compose_report_payload(bundle, options=options)
        return json.dumps(payload, separators=(",", ":"))
    return _render_report_text(bundle)


def compose_report_payload(bundle: EvidenceBundle, *, options: ReportRenderOptions) -> dict[str, object]:
    payload: dict[str, object] = {}
    if options.verbose:
        payload["summary"] = summary_payload(bundle)
        payload["variables"] = grouped_variables_payload(bundle, names=None)
        payload["gdb"] = gdb_payload(bundle, tail=options.tail)
        payload["rtt"] = rtt_payload(bundle, tail=options.tail)
        payload["provenance"] = dict(bundle.provenance)
        payload["parse_warnings"] = list(bundle.parse_warnings)
        return payload
    if options.include_variables:
        payload["variables"] = grouped_variables_payload(bundle, names=options.variable_names)
    if options.include_gdb:
        payload["gdb"] = gdb_payload(bundle, tail=options.tail)
    if options.include_rtt:
        payload["rtt"] = rtt_payload(bundle, tail=options.tail)
    return payload


def summary_payload(bundle: EvidenceBundle) -> dict[str, object]:
    return {
        "snapshot_id": bundle.snapshot_id,
        "captured_at": bundle.captured_at,
        "stop_reason": bundle.stop_reason,
        "pc": bundle.pc,
        "lr": bundle.lr,
        "sp": bundle.sp,
        "frame_count": len(bundle.frames),
        "register_count": len(bundle.registers),
        "variable_count": bundle.variable_evidence.count(),
    }


def grouped_variables_payload(bundle: EvidenceBundle, names: list[str] | None) -> dict[str, list[dict[str, object]]]:
    wanted = {name.lower() for name in (names or [])}
    grouped: dict[str, list[dict[str, object]]] = {}
    matched = 0
    for bucket in VARIABLE_BUCKETS:
        entries = list(bundle.variable_evidence.bucket(bucket))
        if wanted:
            entries = [entry for entry in entries if entry.name.lower() in wanted]
        matched += len(entries)
        grouped[bucket] = [variable_entry_payload(entry) for entry in entries]
    if wanted and matched == 0:
        requested = ", ".join(names or [])
        raise RuntimeError(f"No matches found for requested variables: {requested}")
    return grouped


def variable_entry_payload(entry: VariableEntry) -> dict[str, object]:
    payload = asdict(entry)
    return payload


def gdb_payload(bundle: EvidenceBundle, *, tail: int | None) -> dict[str, object]:
    source = bundle.require_embedded_gdb_source()
    events = list(source.events)
    if tail is not None:
        events = events[-tail:]
    return {
        "raw_text": source.raw_text or "",
        "event_count": len(events),
        "total_event_count": source.event_count,
        "events": [asdict(event) for event in events],
        "embedded": source.embedded,
    }


def rtt_payload(bundle: EvidenceBundle, *, tail: int | None) -> dict[str, object]:
    source = bundle.require_embedded_rtt_source()
    lines = list(source.lines)
    if tail is not None:
        lines = lines[-tail:]
    return {
        "raw_text": source.raw_text or "",
        "line_count": len(lines),
        "total_line_count": source.line_count,
        "lines": lines,
        "embedded": source.embedded,
    }


def _render_report_text(bundle: EvidenceBundle) -> str:
    sections = [
        "DebugOracle Evidence Report",
        "",
        "Session Summary:",
        session_summary(bundle, plain=True),
        "",
        "Stack Trace:",
        stack_section(bundle.frames, plain=True),
        "",
        "Registers:",
        mapping_section(bundle.registers, plain=True),
        "",
        "Variable Summary:",
        variable_section(bundle.variable_evidence, _default_variable_options(), plain=True),
        "Hint: inspect exact variables with `report --vars [NAME ...]`",
        "",
        "Parsing Summary:",
        parsing_summary_section(bundle, plain=True),
        "Hint: inspect embedded GDB events with `report --gdb`",
        "",
        "Unknowns And Gaps:",
        render_bullets(unknowns(bundle, None)),
        "",
        "Source Availability:",
        _source_availability_lines(bundle),
        "Hint: inspect embedded RTT lines with `report --rtt`",
    ]
    return "\n".join(with_parse_warnings(sections, bundle.parse_warnings, header="Parse Warnings:")).rstrip() + "\n"


def _source_availability_lines(bundle: EvidenceBundle) -> str:
    lines = [
        f"- GDB embedded source data: {'present' if bundle.has_embedded_gdb_source else 'absent'}",
        f"- RTT embedded source data: {'present' if bundle.has_embedded_rtt_source else 'absent'}",
    ]
    return "\n".join(lines)


def _default_variable_options():
    class _Options:
        scope = "all"
        names: list[str] = []
        detail = "compact"

    return _Options()
