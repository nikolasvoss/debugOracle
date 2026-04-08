from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from ..artifacts.models import (
    InvestigationArtifact,
    MemoryReadEntry,
    PeripheralRegisterSet,
    RegisterEntry,
    VariableEntry,
    VARIABLE_BUCKETS,
)
from ._evidence_common import (
    VariableRenderOptions,
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
    regs_list_selector: str | None = None
    regs_selectors: list[str] | None = None
    mem_selectors: list[str] | None = None
    allow_unsafe: bool = False

    @property
    def include_variables(self) -> bool:
        return self.variable_names is not None or self.verbose

    @property
    def include_regs_list(self) -> bool:
        return self.regs_list_selector is not None

    @property
    def include_regs(self) -> bool:
        return self.regs_selectors is not None

    @property
    def include_mem(self) -> bool:
        return self.mem_selectors is not None

    @property
    def inspect_mode(self) -> bool:
        return (
            self.include_variables
            or self.include_gdb
            or self.include_rtt
            or self.verbose
            or self.include_regs_list
            or self.include_regs
            or self.include_mem
        )


@dataclass(frozen=True)
class _TextReportState:
    embedded_summary: str
    gap_lines: list[str]
    next_commands: list[str]
    source_availability_lines: str
    unknown_lines: list[str]


def render_report(
    bundle: InvestigationArtifact,
    fmt: str = "text",
    *,
    options: ReportRenderOptions | None = None,
    variable_options=None,
    trust: dict[str, object] | None = None,
) -> str:
    options = options or ReportRenderOptions()
    trust = trust or default_trust_payload()
    if options.inspect_mode:
        payload = compose_report_payload(bundle, options=options, trust=trust)
        return json.dumps(payload, separators=(",", ":"))
    return _render_report_text(bundle, trust=trust, allow_unsafe=options.allow_unsafe)


def compose_report_payload(
    bundle: InvestigationArtifact,
    *,
    options: ReportRenderOptions,
    trust: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {"trust": trust}
    if _should_include_metadata(options):
        payload["metadata"] = report_metadata_payload(bundle)
    if options.verbose:
        payload["summary"] = summary_payload(bundle)
        payload["variables"] = grouped_variables_payload(bundle, names=None)
        payload["gdb"] = gdb_payload(bundle, tail=options.tail)
        payload["rtt"] = rtt_payload(bundle, tail=options.tail)
        if bundle.has_embedded_register_source:
            payload["registers"] = regs_payload(bundle, selectors=[])
        if bundle.has_embedded_memory_source:
            payload["memory"] = memory_payload(bundle, selectors=[])
        payload["provenance"] = dict(bundle.provenance)
        payload["parse_warnings"] = list(bundle.parse_warnings)
        return payload
    if options.include_variables:
        payload["variables"] = grouped_variables_payload(
            bundle, names=options.variable_names
        )
    if options.include_gdb:
        payload["gdb"] = gdb_payload(bundle, tail=options.tail)
    if options.include_rtt:
        payload["rtt"] = rtt_payload(bundle, tail=options.tail)
    if options.include_regs_list:
        payload["registers_list"] = regs_list_payload(
            bundle, selector=options.regs_list_selector
        )
    if options.include_regs:
        payload["registers"] = regs_payload(
            bundle, selectors=options.regs_selectors or []
        )
    if options.include_mem:
        payload["memory"] = memory_payload(
            bundle, selectors=options.mem_selectors or []
        )
    return payload


def _should_include_metadata(options: ReportRenderOptions) -> bool:
    return (
        options.verbose
        or options.include_gdb
        or options.include_rtt
        or options.include_regs_list
        or options.include_regs
        or options.include_mem
    )


def report_metadata_payload(bundle: InvestigationArtifact) -> dict[str, object]:
    freshness_class = bundle.provenance.get("freshness_class", "unknown")
    return {
        "snapshot_id": bundle.snapshot_id,
        "captured_at": bundle.captured_at,
        "freshness_class": freshness_class,
        "source_availability": {
            "gdb": "present" if bundle.has_embedded_gdb_source else "absent",
            "rtt": "present" if bundle.has_embedded_rtt_source else "absent",
            "registers": "present" if bundle.has_embedded_register_source else "absent",
            "memory": "present" if bundle.has_embedded_memory_source else "absent",
        },
    }


def summary_payload(bundle: InvestigationArtifact) -> dict[str, object]:
    payload = {
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
    if bundle.has_embedded_register_source:
        source = bundle.sources.registers
        payload["svd_device_name"] = source.device_name
        payload["svd_peripheral_count"] = source.peripheral_count
        payload["svd_register_count"] = source.register_count
    if bundle.has_embedded_memory_source:
        payload["memory_read_requested_count"] = bundle.sources.memory.requested_count
        payload["memory_read_success_count"] = bundle.sources.memory.success_count
        payload["memory_read_failure_count"] = bundle.sources.memory.failure_count
    return payload


def grouped_variables_payload(
    bundle: InvestigationArtifact,
    names: list[str] | None,
) -> dict[str, list[dict[str, object]]]:
    wanted = {name.lower() for name in names} if names else None
    grouped: dict[str, list[dict[str, object]]] = {}
    matched = 0
    for bucket in VARIABLE_BUCKETS:
        entries = bundle.variable_evidence.bucket(bucket)
        if wanted is not None:
            entries = [entry for entry in entries if entry.name.lower() in wanted]
        matched += len(entries)
        grouped[bucket] = [variable_entry_payload(entry) for entry in entries]
    if wanted is not None and matched == 0:
        requested = ", ".join(names or [])
        raise RuntimeError(f"No matches found for requested variables: {requested}")
    return grouped


def variable_entry_payload(entry: VariableEntry) -> dict[str, object]:
    return asdict(entry)


def gdb_payload(
    bundle: InvestigationArtifact, *, tail: int | None
) -> dict[str, object]:
    source = bundle.require_embedded_gdb_source()
    events = source.events
    if tail is not None:
        events = events[-tail:]
    return {
        "raw_text": source.raw_text or "",
        "event_count": len(events),
        "total_event_count": source.event_count,
        "events": [asdict(event) for event in events],
        "embedded": source.embedded,
    }


def rtt_payload(
    bundle: InvestigationArtifact, *, tail: int | None
) -> dict[str, object]:
    source = bundle.require_embedded_rtt_source()
    lines = source.lines
    if tail is not None:
        lines = lines[-tail:]
    return {
        "raw_text": source.raw_text or "",
        "line_count": len(lines),
        "total_line_count": source.line_count,
        "lines": lines,
        "embedded": source.embedded,
    }


def regs_list_payload(
    bundle: InvestigationArtifact, *, selector: str | None
) -> dict[str, object]:
    source = bundle.require_embedded_register_source()
    if selector in (None, ""):
        peripherals: list[dict[str, object]] = []
        for peripheral in source.peripherals:
            success_count, failure_count, skipped_count = _peripheral_status_counts(
                peripheral
            )
            peripherals.append(
                {
                    "name": peripheral.name,
                    "base_address": peripheral.base_address,
                    "register_count": len(peripheral.registers),
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "skipped_count": skipped_count,
                }
            )
        return {
            "device_name": source.device_name,
            "svd_source": source.svd_source,
            "peripherals": peripherals,
        }
    peripheral = _match_peripheral(source.peripherals, selector)
    if peripheral is None:
        raise RuntimeError(f"No captured peripheral matches requested name: {selector}")
    return {
        "device_name": source.device_name,
        "peripheral": peripheral.name,
        "base_address": peripheral.base_address,
        "registers": [
            {
                "name": register.name,
                "address": register.address,
                "read_status": register.read_status,
            }
            for register in peripheral.registers
        ],
    }


def regs_payload(
    bundle: InvestigationArtifact, *, selectors: list[str]
) -> dict[str, object]:
    source = bundle.require_embedded_register_source()
    if not selectors:
        return {
            "device_name": source.device_name,
            "svd_source": source.svd_source,
            "peripherals": [
                _peripheral_payload(peripheral) for peripheral in source.peripherals
            ],
        }

    wanted_peripherals = {
        selector.lower() for selector in selectors if ":" not in selector
    }
    wanted_registers: dict[str, set[str]] = {}
    for selector in selectors:
        if ":" not in selector:
            continue
        peripheral_name, register_name = selector.split(":", 1)
        wanted_registers.setdefault(peripheral_name.lower(), set()).add(
            register_name.lower()
        )

    matched_peripherals: list[dict[str, object]] = []
    matched_any = False
    for peripheral in source.peripherals:
        peripheral_key = peripheral.name.lower()
        include_peripheral = peripheral_key in wanted_peripherals
        requested_registers = wanted_registers.get(peripheral_key)
        if include_peripheral:
            matched_any = True
            matched_peripherals.append(_peripheral_payload(peripheral))
            continue
        if requested_registers:
            registers = [
                _register_payload(register)
                for register in peripheral.registers
                if register.name.lower() in requested_registers
            ]
            if registers:
                matched_any = True
                matched_peripherals.append(
                    {
                        "name": peripheral.name,
                        "base_address": peripheral.base_address,
                        "warnings": list(peripheral.warnings),
                        "registers": registers,
                    }
                )
    if not matched_any:
        requested = ", ".join(selectors)
        raise RuntimeError(f"No matches found for requested registers: {requested}")
    return {
        "device_name": source.device_name,
        "svd_source": source.svd_source,
        "peripherals": matched_peripherals,
    }


def memory_payload(
    bundle: InvestigationArtifact, *, selectors: list[str]
) -> dict[str, object]:
    source = bundle.require_embedded_memory_source()
    entries = list(source.entries)
    entries.sort(key=_memory_entry_sort_key)
    if selectors:
        wanted = {_parse_selector_pair(selector) for selector in selectors}
        entries = [entry for entry in entries if _memory_entry_pair(entry) in wanted]
        if not entries:
            requested = ", ".join(selectors)
            raise RuntimeError(f"No matches found for requested memory: {requested}")
    return {
        "entries": [_memory_entry_payload(entry) for entry in entries],
    }


def _peripheral_payload(peripheral: PeripheralRegisterSet) -> dict[str, object]:
    return {
        "name": peripheral.name,
        "base_address": peripheral.base_address,
        "warnings": list(peripheral.warnings),
        "registers": [_register_payload(register) for register in peripheral.registers],
    }


def _register_payload(register: RegisterEntry) -> dict[str, object]:
    return asdict(register)


def _peripheral_status_counts(
    peripheral: PeripheralRegisterSet,
) -> tuple[int, int, int]:
    success_count = 0
    failure_count = 0
    skipped_count = 0
    for register in peripheral.registers:
        if register.read_status == "success":
            success_count += 1
        elif register.read_status == "failure":
            failure_count += 1
        elif register.read_status == "skipped":
            skipped_count += 1
    return success_count, failure_count, skipped_count


def _match_peripheral(
    peripherals: list[PeripheralRegisterSet],
    selector: str,
) -> PeripheralRegisterSet | None:
    wanted = selector.lower()
    for peripheral in peripherals:
        if peripheral.name.lower() == wanted:
            return peripheral
    return None


def _render_report_text(
    bundle: InvestigationArtifact,
    *,
    trust: dict[str, object],
    allow_unsafe: bool,
) -> str:
    state = _build_text_report_state(bundle)
    header = _trust_header_lines(trust)
    if trust.get("verdict") == "unsafe" and not allow_unsafe:
        sections = [
            "DebugOracle Evidence Report",
            "",
            *header,
            "",
            "Current State:",
            render_bullets(_current_state_lines(bundle, state=state)),
            "",
            "Trust Reasons:",
            render_bullets(cast(list[str], trust.get("reasons") or []) or ["None"]),
            "",
            "Next Useful Commands:",
            render_bullets(
                [
                    f"`{trust.get('recommended_action', 'dbgoracle fetch --workspace-root .')}`"
                ]
            ),
        ]
        return (
            "\n".join(
                with_parse_warnings(
                    sections, bundle.parse_warnings, header="Parse Warnings Detail:"
                )
            ).rstrip()
            + "\n"
        )

    sections = [
        "DebugOracle Evidence Report",
        "",
        *header,
        "",
        "Current State:",
        render_bullets(_current_state_lines(bundle, state=state)),
        "",
        "Gaps:",
        render_bullets(state.gap_lines),
        "",
        "Next Useful Commands:",
        render_bullets(state.next_commands),
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
        variable_section(
            bundle.variable_evidence, _default_variable_options(), plain=True
        ),
        "",
        "Parsing Summary:",
        parsing_summary_section(bundle, plain=True),
        "",
        "Register Data:",
        _register_availability_lines(bundle),
        "",
        "Unknowns And Gaps:",
        render_bullets(state.unknown_lines),
        "",
        "Source Availability:",
        state.source_availability_lines,
    ]
    return (
        "\n".join(
            with_parse_warnings(
                sections, bundle.parse_warnings, header="Parse Warnings Detail:"
            )
        ).rstrip()
        + "\n"
    )


def _trust_header_lines(trust: dict[str, object]) -> list[str]:
    verdict = str(trust.get("verdict", "unknown")).upper()
    summary = str(trust.get("summary", "Trust status unavailable."))
    recommended_action = str(
        trust.get("recommended_action", "dbgoracle fetch --workspace-root .")
    )
    lines = [
        f"Trust: {verdict}",
        f"- Summary: {summary}",
        f"- Recommended action: `{recommended_action}`",
    ]
    reasons = cast(list[str], trust.get("reasons") or [])
    if reasons:
        lines.append("- Reasons:")
        lines.extend(f"  - {reason}" for reason in reasons)
    return lines


def default_trust_payload() -> dict[str, object]:
    return {
        "verdict": "unknown",
        "summary": "Trust status unavailable.",
        "reasons": [],
        "recommended_action": "dbgoracle fetch --workspace-root .",
    }


def _current_state_lines(
    bundle: InvestigationArtifact, *, state: _TextReportState
) -> list[str]:
    return [
        f"Snapshot ID: {bundle.snapshot_id}",
        f"Stop reason: {bundle.stop_reason or 'unavailable'}",
        f"PC: {bundle.pc or 'unavailable'}",
        f"Embedded evidence: {state.embedded_summary}",
    ]


def _gap_lines(bundle: InvestigationArtifact) -> list[str]:
    gaps: list[str] = []
    if not bundle.has_embedded_gdb_source:
        gaps.append("GDB data: absent.")
    elif not bundle.sources.gdb.events:
        gaps.append("GDB events: absent in embedded source data.")
    if not bundle.has_embedded_rtt_source:
        gaps.append("RTT data: absent.")
    elif not bundle.sources.rtt.lines:
        gaps.append("RTT lines: none were captured in embedded source data.")
    if not bundle.has_embedded_register_source:
        gaps.append(
            "Register data: absent. Use `fetch --svd-file <file>` if peripheral state matters."
        )
    if not bundle.has_embedded_memory_source:
        gaps.append(
            "Memory reads: absent. Use `fetch --mem ADDR:SIZE` when memory evidence matters."
        )
    elif not bundle.sources.memory.entries:
        gaps.append("Memory reads: no entries were captured in embedded source data.")
    if bundle.parse_warnings:
        gaps.append(f"Parse warnings: {len(bundle.parse_warnings)} present.")
    return gaps or ["None"]


def _next_command_lines(bundle: InvestigationArtifact) -> list[str]:
    commands = ["`report --vars [NAME ...]`"]
    if bundle.has_embedded_gdb_source and bundle.sources.gdb.events:
        commands.append("`report --gdb --tail 50`")
    if bundle.has_embedded_rtt_source and bundle.sources.rtt.lines:
        commands.append("`report --rtt --tail 50`")
    if bundle.has_embedded_register_source:
        commands.append("`report --regs-list`")
    else:
        commands.append("`fetch --svd-file <file>`")
    if bundle.has_embedded_memory_source:
        commands.append("`report --mem [ADDR:SIZE ...]`")
    else:
        commands.append("`fetch --mem ADDR:SIZE`")
    return commands


def _embedded_evidence_summary(bundle: InvestigationArtifact) -> str:
    gdb_count = len(bundle.sources.gdb.events) if bundle.has_embedded_gdb_source else 0
    rtt_count = len(bundle.sources.rtt.lines) if bundle.has_embedded_rtt_source else 0
    return ", ".join(
        [
            (
                f"gdb present ({gdb_count} events)"
                if bundle.has_embedded_gdb_source
                else "gdb absent"
            ),
            (
                f"rtt present ({rtt_count} lines)"
                if bundle.has_embedded_rtt_source
                else "rtt absent"
            ),
            f"registers {'present' if bundle.has_embedded_register_source else 'absent'}",
            f"memory {'present' if bundle.has_embedded_memory_source else 'absent'}",
        ]
    )


def _register_availability_lines(bundle: InvestigationArtifact) -> str:
    if not bundle.has_embedded_register_source:
        return "\n".join(
            [
                "- Peripheral register data is not available in this snapshot.",
            ]
        )
    source = bundle.sources.registers
    return "\n".join(
        [
            f"- Peripheral register snapshot data is available for {source.device_name or 'the supplied SVD'}.",
            f"- Captured catalog: {source.peripheral_count} peripherals, {source.register_count} registers, {source.success_count} success, {source.failure_count} failure, {source.skipped_count} skipped.",
            "- Use `report --regs-list` to list captured peripherals.",
            "- Use `report --regs-list GPIOA` to list captured registers in one peripheral.",
            "- Use `report --regs GPIOA:MODER` to inspect stored register values and statuses.",
        ]
    )


def _source_availability_lines(bundle: InvestigationArtifact) -> str:
    gdb_suffix = ""
    if bundle.has_embedded_gdb_source:
        gdb_suffix = f" ({len(bundle.sources.gdb.events)} events)"
    rtt_suffix = ""
    if bundle.has_embedded_rtt_source:
        rtt_suffix = f" ({len(bundle.sources.rtt.lines)} lines)"
    lines = [
        f"- GDB embedded source data: {'present' if bundle.has_embedded_gdb_source else 'absent'}{gdb_suffix}",
        f"- RTT embedded source data: {'present' if bundle.has_embedded_rtt_source else 'absent'}{rtt_suffix}",
        f"- SVD register data: {'present' if bundle.has_embedded_register_source else 'absent'}",
        f"- Memory read data: {'present' if bundle.has_embedded_memory_source else 'absent'}",
    ]
    return "\n".join(lines)


def _memory_entry_payload(entry: MemoryReadEntry) -> dict[str, object]:
    return {
        "status": entry.status,
        "address": entry.address,
        "size": entry.size,
        "data_hex": entry.data_hex,
        "failure_reason": entry.failure_reason,
        "ascii_preview": entry.ascii_preview,
    }


def _parse_selector_pair(selector: str) -> tuple[int, int]:
    if ":" not in selector or selector.count(":") != 1:
        raise RuntimeError(f"Invalid memory selector: {selector}")
    address_text, size_text = selector.split(":", 1)
    try:
        address = int(address_text, 0)
        size = int(size_text, 10)
    except ValueError as error:
        raise RuntimeError(f"Invalid memory selector: {selector}") from error
    return (address, size)


def _memory_entry_pair(entry: MemoryReadEntry) -> tuple[int, int]:
    try:
        address = int(entry.address, 0)
    except ValueError:
        address = 0
    return (address, entry.size)


def _memory_entry_sort_key(entry: MemoryReadEntry) -> tuple[int, int, str]:
    address, size = _memory_entry_pair(entry)
    return (address, size, entry.address)


def _default_variable_options() -> VariableRenderOptions:
    return VariableRenderOptions(scope="all", names=[], detail="compact")


def _build_text_report_state(bundle: InvestigationArtifact) -> _TextReportState:
    gap_lines = _gap_lines(bundle)
    next_commands = _next_command_lines(bundle)
    unknown_lines = unknowns(bundle)
    if "RTT lines: none were captured in embedded source data." in gap_lines:
        unknown_lines = [
            line
            for line in unknown_lines
            if line != "No RTT lines were available for this snapshot."
        ]
    if not unknown_lines:
        if gap_lines:
            unknown_lines = ["No additional evidence gaps beyond the Gaps section."]
        else:
            unknown_lines = [
                "No major evidence gaps detected in the captured snapshot."
            ]
    return _TextReportState(
        embedded_summary=_embedded_evidence_summary(bundle),
        gap_lines=gap_lines,
        next_commands=next_commands,
        source_availability_lines=_source_availability_lines(bundle),
        unknown_lines=unknown_lines,
    )
