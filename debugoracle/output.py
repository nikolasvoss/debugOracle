from __future__ import annotations

from typing import Iterable

from .builder import DEFAULT_RTT_WINDOW, FULL_RTT_WINDOW
from .models import EvidenceBundle, InvestigationRequest, PromptPackage


def build_prompt_package(
    bundle: EvidenceBundle,
    request: InvestigationRequest,
) -> PromptPackage:
    citations = _citations(bundle)
    unknowns = _unknowns(bundle, request)
    summary = _summary(bundle, request)
    appendix = _appendix(bundle, request)
    instructions = _instructions(request)
    return PromptPackage(
        goal=request.goal_text,
        intent=request.intent_text,
        summary=summary,
        evidence_appendix=appendix,
        unknowns_and_gaps=unknowns,
        instructions=instructions,
        citations=citations,
    )


def render_prompt(
    bundle: EvidenceBundle,
    request: InvestigationRequest,
) -> str:
    package = build_prompt_package(bundle, request)
    if request.format == "text":
        return _render_prompt_text(bundle, package)
    return _render_prompt_markdown(bundle, package)


def render_report(bundle: EvidenceBundle, fmt: str = "markdown") -> str:
    if fmt == "text":
        return _render_report_text(bundle)
    return _render_report_markdown(bundle)


def render_snapshot(bundle: EvidenceBundle, fmt: str = "json") -> str:
    if fmt == "json":
        import json

        return json.dumps(bundle.to_dict(), indent=2)
    if fmt == "text":
        return _render_snapshot_text(bundle)
    return _render_snapshot_markdown(bundle)


def _render_prompt_markdown(bundle: EvidenceBundle, package: PromptPackage) -> str:
    lines = [
        "# DebugOracle Prompt Package",
        "",
        "## Goal",
        package.goal,
        "",
    ]
    if package.intent:
        lines.extend(["## Intended System State", package.intent, ""])
    lines.extend(
        [
            "## Summary",
            package.summary,
            "",
            "## Evidence Appendix",
            package.evidence_appendix,
            "",
            "## Unknowns And Gaps",
        ]
    )
    lines.extend([f"- {item}" for item in package.unknowns_and_gaps] or ["- None"])
    lines.extend(
        [
            "",
            "## Instructions For ChatGPT",
            package.instructions,
            "",
            "## Citations",
        ]
    )
    lines.extend([f"- {item}" for item in package.citations])
    return "\n".join(lines).rstrip() + "\n"


def _render_prompt_text(bundle: EvidenceBundle, package: PromptPackage) -> str:
    sections = [
        "DebugOracle Prompt Package",
        "",
        f"Goal: {package.goal}",
    ]
    if package.intent:
        sections.extend(["", "Intended System State:", package.intent])
    sections.extend(
        [
            "",
            "Summary:",
            package.summary,
            "",
            "Evidence Appendix:",
            package.evidence_appendix,
            "",
            "Unknowns And Gaps:",
            _render_bullets(package.unknowns_and_gaps),
            "",
            "Instructions For ChatGPT:",
            package.instructions,
            "",
            "Citations:",
            _render_bullets(package.citations),
        ]
    )
    return "\n".join(sections).rstrip() + "\n"


def _render_report_markdown(bundle: EvidenceBundle) -> str:
    return "\n".join(
        _with_parse_warnings(
            [
            "# DebugOracle Evidence Report",
            "",
            _session_summary(bundle),
            "",
            "## Stack Trace",
            _stack_section(bundle.frames),
            "",
            "## Registers",
            _mapping_section(bundle.registers),
            "",
            "## Watched Values",
            _mapping_section(bundle.watched_values),
            "",
            "## Recent RTT",
            _lines_section(bundle.recent_rtt),
            "",
            "## Parsing Summary",
            _parsing_summary_section(bundle),
            "",
            "## Raw Non-MI Excerpt",
            _lines_section(_non_mi_excerpt(bundle)),
            "",
            "## Unknowns And Gaps",
            _render_bullets(_unknowns(bundle, None), bullet="- "),
            ],
            bundle.parse_warnings,
            header="## Parse Warnings",
        )
    ).rstrip() + "\n"


def _render_report_text(bundle: EvidenceBundle) -> str:
    return "\n".join(
        _with_parse_warnings(
            [
            "DebugOracle Evidence Report",
            "",
            _session_summary(bundle, plain=True),
            "",
            "Stack Trace:",
            _stack_section(bundle.frames, plain=True),
            "",
            "Registers:",
            _mapping_section(bundle.registers, plain=True),
            "",
            "Watched Values:",
            _mapping_section(bundle.watched_values, plain=True),
            "",
            "Recent RTT:",
            _lines_section(bundle.recent_rtt, plain=True),
            "",
            "Parsing Summary:",
            _parsing_summary_section(bundle, plain=True),
            "",
            "Raw Non-MI Excerpt:",
            _lines_section(_non_mi_excerpt(bundle), plain=True),
            "",
            "Unknowns And Gaps:",
            _render_bullets(_unknowns(bundle, None)),
            ],
            bundle.parse_warnings,
            header="Parse Warnings:",
        )
    ).rstrip() + "\n"


def _render_snapshot_markdown(bundle: EvidenceBundle) -> str:
    return _render_report_markdown(bundle)


def _render_snapshot_text(bundle: EvidenceBundle) -> str:
    return _render_report_text(bundle)


def _summary(bundle: EvidenceBundle, request: InvestigationRequest) -> str:
    top = bundle.frames[0] if bundle.frames else None
    location = _frame_label(top) if top else "No stack frame available"
    log_window = bundle.provenance.get("rtt_window", DEFAULT_RTT_WINDOW)
    lines = [
        f"- Snapshot ID: {bundle.snapshot_id}",
        f"- Captured At: {bundle.captured_at}",
        f"- Stop Reason: {bundle.stop_reason or 'unknown'}",
        f"- Current Location: {location}",
        f"- PC/LR/SP: {bundle.pc or 'unknown'} / {bundle.lr or 'unknown'} / {bundle.sp or 'unknown'}",
        f"- Stack Frames: {len(bundle.frames)}",
        f"- Registers Captured: {len(bundle.registers)}",
        f"- Watched Values: {len(bundle.watched_values)}",
        f"- RTT Window Included: {len(bundle.recent_rtt)} lines (configured window {log_window})",
        f"- Requested Goal: {request.goal_text}",
    ]
    if request.detail_level == "full":
        lines.append("- Detail Mode: full")
    else:
        lines.append("- Detail Mode: compact")
    return "\n".join(lines)


def _appendix(bundle: EvidenceBundle, request: InvestigationRequest) -> str:
    rtt_limit = FULL_RTT_WINDOW if request.detail_level == "full" else DEFAULT_RTT_WINDOW
    recent_rtt = bundle.recent_rtt[-rtt_limit:]
    sections = [
        "### Session Context",
        _session_summary(bundle),
        "",
        "### Stack Trace",
        _stack_section(bundle.frames),
        "",
        "### Registers",
        _mapping_section(bundle.registers),
        "",
        "### Watched Values",
        _mapping_section(bundle.watched_values),
        "",
        "### Recent RTT",
        _lines_section(recent_rtt),
        "",
        "### Parsing Summary",
        _parsing_summary_section(bundle),
        "",
        "### Raw Non-MI Excerpt",
        _lines_section(_non_mi_excerpt(bundle)),
        "",
        "### Source Context Placeholder",
        _mapping_section(bundle.source_context),
        "",
        "### Provenance",
        _mapping_section(bundle.provenance),
    ]
    if bundle.parse_warnings:
        sections.extend(
            [
                "",
                "### Parse Warnings",
                _lines_section(bundle.parse_warnings),
            ]
        )
    return "\n".join(sections).rstrip()


def _instructions(request: InvestigationRequest) -> str:
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


def _citations(bundle: EvidenceBundle) -> list[str]:
    gdb_source = bundle.provenance.get("gdb_mi_source", "<unknown>")
    rtt_source = bundle.provenance.get("rtt_source")
    citations = [
        f"C1 Session context and stop state from GDB/MI transcript: {gdb_source}",
        "C2 Stack trace extracted from the latest observed stop-context snapshot",
        "C3 Register values extracted from the latest register-values result record",
        "C4 Watched values extracted from the latest locals/variables result records",
    ]
    if rtt_source:
        citations.append(f"C5 Recent RTT lines from: {rtt_source}")
    else:
        citations.append("C5 RTT evidence unavailable in this snapshot")
    citations.append("C6 Source context is a placeholder and was not collected in v1")
    return citations


def _unknowns(bundle: EvidenceBundle, request: InvestigationRequest | None) -> list[str]:
    unknowns: list[str] = []
    _, _, mi_parse_error_count = _parsing_summary_counts(bundle)
    if bundle.stop_reason is None:
        unknowns.append("No stop reason was found in the parsed GDB/MI transcript.")
    if not bundle.frames:
        unknowns.append("No stack trace was available in the parsed transcript.")
    if not bundle.registers:
        unknowns.append("No register-values record was found in the parsed transcript.")
    if not bundle.watched_values:
        unknowns.append("No watched values or locals were captured in the parsed transcript.")
    if not bundle.recent_rtt:
        unknowns.append("No RTT lines were available for this snapshot.")
    if mi_parse_error_count:
        unknowns.append(
            f"MI parse errors detected: {mi_parse_error_count} (see Parsing Summary)."
        )
    if request and request.intent_text is None:
        unknowns.append("No intended system state text was provided.")
    if request and len(request.goal_text.strip()) < 10:
        unknowns.append("The requested goal is very short and may be underspecified.")
    return unknowns or ["No major evidence gaps detected in the packaged snapshot."]


def _session_summary(bundle: EvidenceBundle, plain: bool = False) -> str:
    top = bundle.frames[0] if bundle.frames else None
    location = _frame_label(top) if top else "No stack frame available"
    prefix = "" if plain else ""
    lines = [
        f"{prefix}- Snapshot ID: {bundle.snapshot_id}",
        f"{prefix}- Captured At: {bundle.captured_at}",
        f"{prefix}- Stop Reason: {bundle.stop_reason or 'unknown'}",
        f"{prefix}- Current Location: {location}",
        f"{prefix}- PC/LR/SP: {bundle.pc or 'unknown'} / {bundle.lr or 'unknown'} / {bundle.sp or 'unknown'}",
    ]
    return "\n".join(lines)


def _stack_section(frames: list, plain: bool = False) -> str:
    if not frames:
        return "- None" if not plain else "- None"
    lines = []
    for frame in frames:
        label = _frame_label(frame)
        level = frame.level if frame.level is not None else "?"
        lines.append(f"- #{level}: {label}")
    return "\n".join(lines)


def _frame_label(frame) -> str:
    if frame is None:
        return "unknown"
    file_part = frame.fullname or frame.file or "<unknown-file>"
    line_part = f":{frame.line}" if frame.line is not None else ""
    func_part = frame.func or "<unknown-func>"
    addr_part = frame.addr or "<unknown-addr>"
    return f"{func_part} at {file_part}{line_part} ({addr_part})"


def _mapping_section(mapping: dict, plain: bool = False) -> str:
    if not mapping:
        return "- None"
    return "\n".join(f"- {key}: {value}" for key, value in mapping.items())


def _lines_section(lines: Iterable[str], plain: bool = False) -> str:
    lines = list(lines)
    if not lines:
        return "- None"
    return "\n".join(f"- {line}" for line in lines)


def _render_bullets(items: Iterable[str], bullet: str = "- ") -> str:
    return "\n".join(f"{bullet}{item}" for item in items)


def _parsing_summary_counts(bundle: EvidenceBundle) -> tuple[int, int, int]:
    mi_record_count = int(bundle.provenance.get("mi_record_count", 0) or 0)
    non_mi_line_count = int(bundle.provenance.get("non_mi_line_count", 0) or 0)
    mi_parse_error_count = int(bundle.provenance.get("mi_parse_error_count", 0) or 0)

    if not any((mi_record_count, non_mi_line_count, mi_parse_error_count)):
        for event in bundle.session_events:
            if event.kind == "non_mi_line":
                non_mi_line_count += 1
            elif event.kind == "parse_error":
                mi_parse_error_count += 1
            else:
                mi_record_count += 1

    return mi_record_count, non_mi_line_count, mi_parse_error_count


def _parsing_summary_section(bundle: EvidenceBundle, plain: bool = False) -> str:
    mi_record_count, non_mi_line_count, mi_parse_error_count = _parsing_summary_counts(bundle)
    lines = [
        f"- MI records parsed: {mi_record_count}",
        f"- Non-MI lines retained: {non_mi_line_count}",
        f"- MI parse errors: {mi_parse_error_count}",
    ]
    return "\n".join(lines)


def _non_mi_excerpt(bundle: EvidenceBundle, limit: int = 50) -> list[str]:
    lines = [
        event.payload.get("raw", "")
        for event in bundle.session_events
        if event.kind == "non_mi_line"
    ]
    lines = [line for line in lines if line]
    if limit <= 0:
        return []
    return lines[-limit:]


def _with_parse_warnings(
    sections: list[str],
    parse_warnings: list[str],
    *,
    header: str,
) -> list[str]:
    if not parse_warnings:
        return sections
    return [*sections, "", header, _lines_section(parse_warnings)]
