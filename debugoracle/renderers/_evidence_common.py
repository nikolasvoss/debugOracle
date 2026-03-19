from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..artifacts.models import (
    EvidenceBundle,
    InvestigationRequest,
    VariableEntry,
    VariableEvidence,
    VARIABLE_BUCKETS,
)
from ..builder import DEFAULT_RTT_WINDOW, FULL_RTT_WINDOW

COMPACT_VARIABLE_LIMIT = 5


@dataclass
class VariableRenderOptions:
    scope: str = "all"
    names: list[str] = field(default_factory=list)
    detail: str = "compact"


def summary(bundle: EvidenceBundle, request: InvestigationRequest) -> str:
    top = bundle.frames[0] if bundle.frames else None
    location = frame_label(top) if top else "No stack frame available"
    log_window = bundle.provenance.get("rtt_window", DEFAULT_RTT_WINDOW)
    variable_options = variable_options_from_request(request)
    lines = [
        f"- Snapshot ID: {bundle.snapshot_id}",
        f"- Captured At: {bundle.captured_at}",
        f"- Stop Reason: {bundle.stop_reason or 'unknown'}",
        f"- Current Location: {location}",
        f"- PC/LR/SP: {bundle.pc or 'unknown'} / {bundle.lr or 'unknown'} / {bundle.sp or 'unknown'}",
        f"- Stack Frames: {len(bundle.frames)}",
        f"- Registers Captured: {len(bundle.registers)}",
        f"- Variable Entries: {bundle.variable_evidence.count()}",
        f"- RTT Window Included: {len(bundle.recent_rtt)} lines (configured window {log_window})",
        f"- Requested Goal: {request.goal_text}",
    ]
    evidence_quality = bundle.provenance.get("evidence_quality_score")
    if evidence_quality is not None:
        lines.append(f"- Evidence Quality Score: {evidence_quality}/100")
    if request.detail_level == "full":
        lines.append("- Detail Mode: full")
    else:
        lines.append("- Detail Mode: compact")
    lines.append(f"- Variable Scope: {variable_options.scope}")
    lines.append(f"- Variable Detail: {variable_options.detail}")
    return "\n".join(lines)


def appendix(bundle: EvidenceBundle, request: InvestigationRequest) -> str:
    rtt_limit = FULL_RTT_WINDOW if request.detail_level == "full" else DEFAULT_RTT_WINDOW
    recent_rtt = bundle.recent_rtt[-rtt_limit:]
    variable_options = variable_options_from_request(request)
    sections = [
        "### Session Context",
        session_summary(bundle),
        "",
        "### Stack Trace",
        stack_section(bundle.frames),
        "",
        "### Registers",
        mapping_section(bundle.registers),
        "",
        "### Variable Evidence",
        variable_section(bundle.variable_evidence, variable_options),
        "",
        "### Recent RTT",
        lines_section(recent_rtt),
        "",
        "### Parsing Summary",
        parsing_summary_section(bundle),
        "",
        "### Raw Non-MI Excerpt",
        lines_section(non_mi_excerpt(bundle)),
        "",
        "### Source Context",
        mapping_section(bundle.source_context),
        "",
        "### Provenance",
        mapping_section(bundle.provenance),
    ]
    if bundle.parse_warnings:
        sections.extend(["", "### Parse Warnings", lines_section(bundle.parse_warnings)])
    return "\n".join(sections).rstrip()


def instructions(request: InvestigationRequest) -> str:
    return "\n".join(
        [
            "- Use the provided evidence bundle as the primary source of truth.",
            "- Separate observed facts from inferred hypotheses.",
            "- Call out missing or ambiguous evidence before reaching conclusions.",
            "- If an intended system state is provided, compare it explicitly against the observed state.",
            "- Recommend concrete next debug steps that gather more evidence without assuming unsupported facts.",
            f"- Answer the user goal directly: {request.goal_text}",
        ]
    )


def citations(bundle: EvidenceBundle) -> list[str]:
    gdb_source = bundle.provenance.get("gdb_mi_source", "<unknown>")
    rtt_source = bundle.provenance.get("rtt_source")
    citations = [
        f"C1 Session context and stop state from GDB/MI transcript: {gdb_source}",
        "C2 Stack trace extracted from the latest observed stop-context snapshot",
        "C3 Register values extracted from the latest register-values result record",
        "C4 Variable evidence extracted from the latest locals/variables/watchpoint records",
    ]
    if rtt_source:
        citations.append(f"C5 Recent RTT lines from: {rtt_source}")
    else:
        citations.append("C5 RTT evidence unavailable in this snapshot")
    return citations


def unknowns(bundle: EvidenceBundle, request: InvestigationRequest | None) -> list[str]:
    unknowns_list: list[str] = []
    _, _, mi_parse_error_count = parsing_summary_counts(bundle)
    if bundle.stop_reason is None:
        unknowns_list.append("No stop reason was found in the parsed GDB/MI transcript.")
    if not bundle.frames:
        unknowns_list.append("No stack trace was available in the parsed transcript.")
    if not bundle.registers:
        unknowns_list.append("No register-values record was found in the parsed transcript.")
    if bundle.variable_evidence.count() == 0:
        unknowns_list.append("No variable evidence was captured in the parsed transcript.")
    if not bundle.recent_rtt:
        unknowns_list.append("No RTT lines were available for this snapshot.")
    if evidence_quality := evidence_quality_score(bundle):
        if evidence_quality < 60:
            unknowns_list.append(
                f"Evidence quality is reduced ({evidence_quality}/100), which may hide state transitions."
            )
    if mi_parse_error_count:
        unknowns_list.append(f"MI parse errors detected: {mi_parse_error_count} (see Parsing Summary).")
    for warning in critical_warnings(bundle):
        unknowns_list.append(f"Critical parser warning: {warning}")
    if request and request.intent_text is None:
        unknowns_list.append("No intended system state text was provided.")
    if request and len(request.goal_text.strip()) < 10:
        unknowns_list.append("The requested goal is very short and may be underspecified.")
    return unknowns_list or ["No major evidence gaps detected in the packaged snapshot."]


def session_summary(bundle: EvidenceBundle, plain: bool = False) -> str:
    top = bundle.frames[0] if bundle.frames else None
    location = frame_label(top) if top else "No stack frame available"
    prefix = "" if plain else ""
    lines = [
        f"{prefix}- Snapshot ID: {bundle.snapshot_id}",
        f"{prefix}- Captured At: {bundle.captured_at}",
        f"{prefix}- Stop Reason: {bundle.stop_reason or 'unknown'}",
        f"{prefix}- Current Location: {location}",
        f"{prefix}- PC/LR/SP: {bundle.pc or 'unknown'} / {bundle.lr or 'unknown'} / {bundle.sp or 'unknown'}",
    ]
    return "\n".join(lines)


def stack_section(frames: list, plain: bool = False) -> str:
    if not frames:
        return "- None"
    lines = []
    for frame in frames:
        level = frame.level if frame.level is not None else "?"
        lines.append(f"- #{level}: {frame_label(frame)}")
    return "\n".join(lines)


def frame_label(frame) -> str:
    if frame is None:
        return "unknown"
    file_part = frame.fullname or frame.file or "<unknown-file>"
    line_part = f":{frame.line}" if frame.line is not None else ""
    func_part = frame.func or "<unknown-func>"
    addr_part = frame.addr or "<unknown-addr>"
    return f"{func_part} at {file_part}{line_part} ({addr_part})"


def mapping_section(mapping: dict, plain: bool = False) -> str:
    if not mapping:
        return "- None"
    return "\n".join(f"- {key}: {value}" for key, value in mapping.items())


def lines_section(lines: Iterable[str], plain: bool = False) -> str:
    lines = list(lines)
    if not lines:
        return "- None"
    return "\n".join(f"- {line}" for line in lines)


def render_bullets(items: Iterable[str], bullet: str = "- ") -> str:
    return "\n".join(f"{bullet}{item}" for item in items)


def variable_options_from_request(request: InvestigationRequest) -> VariableRenderOptions:
    return VariableRenderOptions(
        scope=request.var_scope,
        names=list(request.var_names),
        detail=request.var_detail,
    )


def variable_options_from_args(args: object) -> VariableRenderOptions:
    scope = getattr(args, "var_scope", "all")
    names = list(getattr(args, "var_name", []) or [])
    detail = getattr(args, "var_detail", "compact")
    return VariableRenderOptions(scope=scope, names=names, detail=detail)


def variable_section(
    evidence: VariableEvidence,
    options: VariableRenderOptions,
    *,
    plain: bool = False,
) -> str:
    sections: list[str] = []
    for bucket in VARIABLE_BUCKETS:
        entries = list(filtered_variable_entries(evidence.bucket(bucket), options, bucket))
        title = bucket_heading(bucket)
        sections.append(f"- {title}: {len(entries)} total")
        if not entries:
            sections.append("  - None")
            continue
        display_entries = entries if options.detail == "full" else entries[:COMPACT_VARIABLE_LIMIT]
        for entry in display_entries:
            sections.append(f"  - {format_variable_entry(entry)}")
        omitted = len(entries) - len(display_entries)
        if omitted > 0:
            sections.append(f"  - ... {omitted} more omitted")
    return "\n".join(sections)


def filtered_variable_entries(
    entries: list[VariableEntry],
    options: VariableRenderOptions,
    bucket: str,
) -> list[VariableEntry]:
    if options.scope != "all" and normalize_scope(options.scope) != bucket:
        return []
    if not options.names:
        return entries
    wanted = {name.lower() for name in options.names}
    return [entry for entry in entries if entry.name.lower() in wanted]


def normalize_scope(scope: str) -> str:
    mapping = {
        "all": "all",
        "local": "locals",
        "locals": "locals",
        "global": "globals",
        "globals": "globals",
        "watchpoint": "watchpoints",
        "watchpoints": "watchpoints",
        "unknown": "unknown",
    }
    return mapping.get(scope, scope)


def bucket_heading(bucket: str) -> str:
    return {
        "locals": "Locals",
        "globals": "Globals",
        "watchpoints": "Watchpoints",
        "unknown": "Unknown Classification",
    }.get(bucket, bucket.title())


def format_variable_entry(entry: VariableEntry) -> str:
    value = entry.value if entry.value is not None else "<unavailable>"
    context = []
    if entry.frame:
        context.append(entry.frame)
    if entry.availability != "captured":
        context.append(entry.availability)
    if entry.origin:
        context.append(entry.origin)
    suffix = f" ({', '.join(context)})" if context else ""
    return f"{entry.name}: {value}{suffix}"


def parsing_summary_counts(bundle: EvidenceBundle) -> tuple[int, int, int]:
    mi_record_count = int(bundle.provenance.get("mi_record_count", 0) or 0)
    non_mi_line_count = int(bundle.provenance.get("non_mi_line_count", 0) or 0)
    mi_parse_error_count = int(bundle.provenance.get("mi_parse_error_count", 0) or 0)
    parse_event_counts = coerce_count_map(bundle.provenance.get("parse_event_counts"))
    if not mi_record_count and parse_event_counts:
        mi_record_count = sum(
            value
            for kind, value in parse_event_counts.items()
            if kind not in {"non_mi_line", "prompt-marker", "console-output", "missing-rtt", "critical-missing-input", "critical-mi-parse-errors"}
            and not kind.startswith("mi-parse-error")
        )
    if not non_mi_line_count and parse_event_counts:
        non_mi_line_count = sum(parse_event_counts.get(kind, 0) for kind in ("non_mi_line", "prompt-marker", "console-output"))
    if not mi_parse_error_count and parse_event_counts:
        mi_parse_error_count = sum(value for kind, value in parse_event_counts.items() if kind.startswith("mi-parse-error"))
    return mi_record_count, non_mi_line_count, mi_parse_error_count


def parsing_summary_section(bundle: EvidenceBundle, plain: bool = False) -> str:
    mi_record_count, non_mi_line_count, mi_parse_error_count = parsing_summary_counts(bundle)
    parse_event_counts = coerce_count_map(bundle.provenance.get("parse_event_counts"))
    parse_event_severity_counts = coerce_count_map(bundle.provenance.get("parse_event_severity_counts"))
    parse_patterns = coerce_pattern_counts(bundle.provenance.get("non_mi_pattern_counts"))
    quality = evidence_quality_score(bundle)
    lines = [
        f"- MI records parsed: {mi_record_count}",
        f"- Non-MI lines retained: {non_mi_line_count}",
        f"- MI parse errors: {mi_parse_error_count}",
    ]
    if quality is not None:
        lines.append(f"- Evidence Quality Score: {quality}/100")
    if parse_event_severity_counts:
        warn_count = parse_event_severity_counts.get("warn", 0)
        info_count = parse_event_severity_counts.get("info", 0)
        lines.append(f"- Event severity: info={info_count}, warn={warn_count}")
    if parse_patterns:
        lines.extend(["- Top non-MI patterns:"] + [f"  - {item['pattern']} (repeated {item['count']} times)" for item in parse_patterns[:6]])
    if parse_event_counts:
        lines.append("- Event types:")
        for kind in sorted(parse_event_counts):
            lines.append(f"  - {kind}: {parse_event_counts[kind]}")
    return "\n".join(lines)


def non_mi_excerpt(bundle: EvidenceBundle, limit: int = 50) -> list[str]:
    events = [event for event in bundle.session_events if event.kind in {"non_mi_line", "console-output", "prompt-marker"}]
    if not events or limit <= 0:
        return []
    noise_lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for event in reversed(events):
        payload = event.payload or {}
        normalized = payload.get("normalized")
        raw = normalized if isinstance(normalized, str) else None
        if raw is None:
            raw_value = payload.get("raw")
            raw = raw_value if isinstance(raw_value, str) else None
        if raw is None:
            continue
        raw_one_line = raw.replace("\n", "\\n")
        key = (event.kind, raw_one_line)
        if key in seen:
            continue
        seen.add(key)
        line_marker = payload.get("line")
        marker = f"L{line_marker}: " if line_marker is not None else ""
        noise_lines.append(f"{event.kind}:{marker}{raw_one_line}")
        if len(noise_lines) >= limit:
            break
    noise_lines.reverse()
    lines: list[str] = []
    noise_patterns = coerce_pattern_counts(bundle.provenance.get("non_mi_pattern_counts"))
    if noise_patterns:
        lines.append("Top non-MI patterns:")
        lines.extend([f"  {item['pattern']} (repeated {item['count']} times)" for item in noise_patterns[:3]])
    if noise_lines:
        lines.append("Latest distinct non-MI samples:")
        lines.extend(noise_lines)
    return lines


def evidence_quality_score(bundle: EvidenceBundle) -> int | None:
    value = bundle.provenance.get("evidence_quality_score")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def critical_warnings(bundle: EvidenceBundle) -> list[str]:
    raw = bundle.provenance.get("critical_warnings")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    return []


def coerce_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        try:
            counts[key] = int(item)
        except (TypeError, ValueError):
            counts[key] = 0
    return counts


def coerce_pattern_counts(value: object) -> list[dict[str, int | str]]:
    if not isinstance(value, list):
        return []
    patterns: list[dict[str, int | str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern")
        count = item.get("count")
        if not isinstance(pattern, str):
            continue
        try:
            parsed_count = int(count)
        except (TypeError, ValueError):
            continue
        if parsed_count <= 0:
            continue
        patterns.append({"pattern": sanitize_pattern_for_display(pattern), "count": parsed_count})
    return patterns


def sanitize_pattern_for_display(value: str) -> str:
    normalized = value.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    return " ".join(normalized.split()) or "<empty>"


def with_parse_warnings(sections: list[str], parse_warnings: list[str], *, header: str) -> list[str]:
    if not parse_warnings:
        return sections
    return [*sections, "", header, lines_section(parse_warnings)]
