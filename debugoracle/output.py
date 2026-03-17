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
    evidence_quality = bundle.provenance.get("evidence_quality_score")
    if evidence_quality is not None:
        lines.append(f"- Evidence Quality Score: {evidence_quality}/100")
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
        "### Source Context",
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
    if evidence_quality := _evidence_quality_score(bundle):
        if evidence_quality < 60:
            unknowns.append(
                f"Evidence quality is reduced ({evidence_quality}/100), which may hide state transitions."
            )
    if mi_parse_error_count:
        unknowns.append(
            f"MI parse errors detected: {mi_parse_error_count} (see Parsing Summary)."
        )
    for warning in _critical_warnings(bundle):
        unknowns.append(f"Critical parser warning: {warning}")
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
    parse_event_counts = _coerce_count_map(bundle.provenance.get("parse_event_counts"))

    if not mi_record_count and parse_event_counts:
        mi_record_count = sum(
            value
            for kind, value in parse_event_counts.items()
            if kind
            not in {
                "non_mi_line",
                "prompt-marker",
                "console-output",
                "missing-rtt",
                "critical-missing-input",
                "critical-mi-parse-errors",
            }
            and not kind.startswith("mi-parse-error")
        )
    if not non_mi_line_count and parse_event_counts:
        non_mi_line_count = sum(
            parse_event_counts.get(kind, 0)
            for kind in ("non_mi_line", "prompt-marker", "console-output")
        )
    if not mi_parse_error_count and parse_event_counts:
        mi_parse_error_count = sum(
            value
            for kind, value in parse_event_counts.items()
            if kind.startswith("mi-parse-error")
        )

    return mi_record_count, non_mi_line_count, mi_parse_error_count


def _parsing_summary_section(bundle: EvidenceBundle, plain: bool = False) -> str:
    mi_record_count, non_mi_line_count, mi_parse_error_count = _parsing_summary_counts(bundle)
    parse_event_counts = _coerce_count_map(bundle.provenance.get("parse_event_counts"))
    parse_event_severity_counts = _coerce_count_map(
        bundle.provenance.get("parse_event_severity_counts")
    )
    parse_patterns = _coerce_pattern_counts(bundle.provenance.get("non_mi_pattern_counts"))
    quality_score = _evidence_quality_score(bundle)
    lines = [
        f"- MI records parsed: {mi_record_count}",
        f"- Non-MI lines retained: {non_mi_line_count}",
        f"- MI parse errors: {mi_parse_error_count}",
    ]
    if quality_score is not None:
        lines.append(f"- Evidence Quality Score: {quality_score}/100")
    if parse_event_severity_counts:
        warn_count = parse_event_severity_counts.get("warn", 0)
        info_count = parse_event_severity_counts.get("info", 0)
        lines.append(f"- Event severity: info={info_count}, warn={warn_count}")
    if parse_patterns:
        lines.extend(
            ["- Top non-MI patterns:"]
            + [
                f"  - {item['pattern']} (repeated {item['count']} times)"
                for item in parse_patterns[:6]
            ]
        )
    if parse_event_counts:
        lines.append("- Event types:")
        for kind in sorted(parse_event_counts):
            lines.append(f"  - {kind}: {parse_event_counts[kind]}")
    return "\n".join(lines)


def _non_mi_excerpt(bundle: EvidenceBundle, limit: int = 50) -> list[str]:
    events = [
        event
        for event in bundle.session_events
        if event.kind in {"non_mi_line", "console-output", "prompt-marker"}
    ]
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
    noise_patterns = _coerce_pattern_counts(bundle.provenance.get("non_mi_pattern_counts"))
    if noise_patterns:
        lines.append("Top non-MI patterns:")
        lines.extend(
            [
                f"  {item['pattern']} (repeated {item['count']} times)"
                for item in noise_patterns[:3]
            ]
        )
    if noise_lines:
        lines.append("Latest distinct non-MI samples:")
        lines.extend(noise_lines)
    return lines


def _evidence_quality_score(bundle: EvidenceBundle) -> int | None:
    value = bundle.provenance.get("evidence_quality_score")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _critical_warnings(bundle: EvidenceBundle) -> list[str]:
    raw = bundle.provenance.get("critical_warnings")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    return []


def _coerce_count_map(value: object) -> dict[str, int]:
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


def _coerce_pattern_counts(value: object) -> list[dict[str, int | str]]:
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
        patterns.append(
            {
                "pattern": _sanitize_pattern_for_display(pattern),
                "count": parsed_count,
            }
        )
    return patterns


def _sanitize_pattern_for_display(value: str) -> str:
    normalized = (
        value.replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return " ".join(normalized.split()) or "<empty>"


def _with_parse_warnings(
    sections: list[str],
    parse_warnings: list[str],
    *,
    header: str,
) -> list[str]:
    if not parse_warnings:
        return sections
    return [*sections, "", header, _lines_section(parse_warnings)]
