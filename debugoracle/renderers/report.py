from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..artifacts.models import EvidenceBundle, PeripheralRegisterSet, RegisterEntry, VariableEntry, VARIABLE_BUCKETS
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
    regs_list_selector: str | None = None
    regs_selectors: list[str] | None = None

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
    def inspect_mode(self) -> bool:
        return (
            self.include_variables
            or self.include_gdb
            or self.include_rtt
            or self.verbose
            or self.include_regs_list
            or self.include_regs
        )


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
    if _should_include_metadata(options):
        payload["metadata"] = report_metadata_payload(bundle)
    if options.verbose:
        payload["summary"] = summary_payload(bundle)
        payload["variables"] = grouped_variables_payload(bundle, names=None)
        payload["gdb"] = gdb_payload(bundle, tail=options.tail)
        payload["rtt"] = rtt_payload(bundle, tail=options.tail)
        if bundle.has_embedded_register_source:
            payload["registers"] = regs_payload(bundle, selectors=[])
        payload["provenance"] = dict(bundle.provenance)
        payload["parse_warnings"] = list(bundle.parse_warnings)
        return payload
    if options.include_variables:
        payload["variables"] = grouped_variables_payload(bundle, names=options.variable_names)
    if options.include_gdb:
        payload["gdb"] = gdb_payload(bundle, tail=options.tail)
    if options.include_rtt:
        payload["rtt"] = rtt_payload(bundle, tail=options.tail)
    if options.include_regs_list:
        payload["registers_list"] = regs_list_payload(bundle, selector=options.regs_list_selector)
    if options.include_regs:
        payload["registers"] = regs_payload(bundle, selectors=options.regs_selectors or [])
    return payload


def _should_include_metadata(options: ReportRenderOptions) -> bool:
    return (
        options.verbose
        or options.include_gdb
        or options.include_rtt
        or options.include_regs_list
        or options.include_regs
    )


def report_metadata_payload(bundle: EvidenceBundle) -> dict[str, object]:
    freshness_class = bundle.provenance.get("freshness_class", "unknown")
    return {
        "snapshot_id": bundle.snapshot_id,
        "captured_at": bundle.captured_at,
        "freshness_class": freshness_class,
        "source_availability": {
            "gdb": "present" if bundle.has_embedded_gdb_source else "absent",
            "rtt": "present" if bundle.has_embedded_rtt_source else "absent",
            "registers": "present" if bundle.has_embedded_register_source else "absent",
        },
    }


def summary_payload(bundle: EvidenceBundle) -> dict[str, object]:
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
    return payload


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


def regs_list_payload(bundle: EvidenceBundle, *, selector: str | None) -> dict[str, object]:
    source = bundle.require_embedded_register_source()
    if selector in (None, ""):
        return {
            "device_name": source.device_name,
            "svd_source": source.svd_source,
            "peripherals": [
                {
                    "name": peripheral.name,
                    "base_address": peripheral.base_address,
                    "register_count": len(peripheral.registers),
                    "success_count": sum(1 for register in peripheral.registers if register.read_status == "success"),
                    "failure_count": sum(1 for register in peripheral.registers if register.read_status == "failure"),
                    "skipped_count": sum(1 for register in peripheral.registers if register.read_status == "skipped"),
                }
                for peripheral in source.peripherals
            ],
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


def regs_payload(bundle: EvidenceBundle, *, selectors: list[str]) -> dict[str, object]:
    source = bundle.require_embedded_register_source()
    if not selectors:
        return {
            "device_name": source.device_name,
            "svd_source": source.svd_source,
            "peripherals": [_peripheral_payload(peripheral) for peripheral in source.peripherals],
        }

    wanted_peripherals = {selector.lower() for selector in selectors if ":" not in selector}
    wanted_registers: dict[str, set[str]] = {}
    for selector in selectors:
        if ":" not in selector:
            continue
        peripheral_name, register_name = selector.split(":", 1)
        wanted_registers.setdefault(peripheral_name.lower(), set()).add(register_name.lower())

    matched_peripherals: list[dict[str, object]] = []
    matched_any = False
    for peripheral in source.peripherals:
        peripheral_key = peripheral.name.lower()
        include_peripheral = peripheral_key in wanted_peripherals
        requested_registers = wanted_registers.get(peripheral_key, set())
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


def _peripheral_payload(peripheral: PeripheralRegisterSet) -> dict[str, object]:
    return {
        "name": peripheral.name,
        "base_address": peripheral.base_address,
        "warnings": list(peripheral.warnings),
        "registers": [_register_payload(register) for register in peripheral.registers],
    }


def _register_payload(register: RegisterEntry) -> dict[str, object]:
    payload = asdict(register)
    return payload


def _match_peripheral(peripherals: list[PeripheralRegisterSet], selector: str) -> PeripheralRegisterSet | None:
    wanted = selector.lower()
    for peripheral in peripherals:
        if peripheral.name.lower() == wanted:
            return peripheral
    return None


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
        "Register Data:",
        _register_availability_lines(bundle),
        "",
        "Unknowns And Gaps:",
        render_bullets(unknowns(bundle, None)),
        "",
        "Source Availability:",
        _source_availability_lines(bundle),
        "Hint: inspect embedded RTT lines with `report --rtt`",
    ]
    return "\n".join(with_parse_warnings(sections, bundle.parse_warnings, header="Parse Warnings:")).rstrip() + "\n"


def _register_availability_lines(bundle: EvidenceBundle) -> str:
    if not bundle.has_embedded_register_source:
        return "\n".join([
            "- Peripheral register data is not available in this snapshot.",
            "- Re-run `fetch --svd-file <file>` to capture peripheral register values.",
        ])
    source = bundle.sources.registers
    return "\n".join([
        f"- Peripheral register snapshot data is available for {source.device_name or 'the supplied SVD'}.",
        f"- Captured catalog: {source.peripheral_count} peripherals, {source.register_count} registers, {source.success_count} success, {source.failure_count} failure, {source.skipped_count} skipped.",
        "- Use `report --regs-list` to list captured peripherals.",
        "- Use `report --regs-list GPIOA` to list captured registers in one peripheral.",
        "- Use `report --regs GPIOA:MODER` to inspect stored register values and statuses.",
    ])


def _source_availability_lines(bundle: EvidenceBundle) -> str:
    lines = [
        f"- GDB embedded source data: {'present' if bundle.has_embedded_gdb_source else 'absent'}",
        f"- RTT embedded source data: {'present' if bundle.has_embedded_rtt_source else 'absent'}",
        f"- SVD register data: {'present' if bundle.has_embedded_register_source else 'absent'}",
    ]
    return "\n".join(lines)


def _default_variable_options():
    class _Options:
        scope = "all"
        names: list[str] = []
        detail = "compact"

    return _Options()
