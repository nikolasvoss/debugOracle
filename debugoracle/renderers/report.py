from __future__ import annotations

from ..artifacts.models import EvidenceBundle
from ._evidence_common import (
    lines_section,
    mapping_section,
    non_mi_excerpt,
    parsing_summary_section,
    render_bullets,
    session_summary,
    stack_section,
    unknowns,
    with_parse_warnings,
)


def render_report(bundle: EvidenceBundle, fmt: str = "markdown") -> str:
    if fmt == "text":
        return _render_report_text(bundle)
    return _render_report_markdown(bundle)


def _render_report_markdown(bundle: EvidenceBundle) -> str:
    return "\n".join(
        with_parse_warnings(
            [
                "# DebugOracle Evidence Report",
                "",
                session_summary(bundle),
                "",
                "## Stack Trace",
                stack_section(bundle.frames),
                "",
                "## Registers",
                mapping_section(bundle.registers),
                "",
                "## Watched Values",
                mapping_section(bundle.watched_values),
                "",
                "## Recent RTT",
                lines_section(bundle.recent_rtt),
                "",
                "## Parsing Summary",
                parsing_summary_section(bundle),
                "",
                "## Raw Non-MI Excerpt",
                lines_section(non_mi_excerpt(bundle)),
                "",
                "## Unknowns And Gaps",
                render_bullets(unknowns(bundle, None), bullet="- "),
            ],
            bundle.parse_warnings,
            header="## Parse Warnings",
        )
    ).rstrip() + "\n"


def _render_report_text(bundle: EvidenceBundle) -> str:
    return "\n".join(
        with_parse_warnings(
            [
                "DebugOracle Evidence Report",
                "",
                session_summary(bundle, plain=True),
                "",
                "Stack Trace:",
                stack_section(bundle.frames, plain=True),
                "",
                "Registers:",
                mapping_section(bundle.registers, plain=True),
                "",
                "Watched Values:",
                mapping_section(bundle.watched_values, plain=True),
                "",
                "Recent RTT:",
                lines_section(bundle.recent_rtt, plain=True),
                "",
                "Parsing Summary:",
                parsing_summary_section(bundle, plain=True),
                "",
                "Raw Non-MI Excerpt:",
                lines_section(non_mi_excerpt(bundle), plain=True),
                "",
                "Unknowns And Gaps:",
                render_bullets(unknowns(bundle, None)),
            ],
            bundle.parse_warnings,
            header="Parse Warnings:",
        )
    ).rstrip() + "\n"
