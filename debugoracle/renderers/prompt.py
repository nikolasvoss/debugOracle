from __future__ import annotations

from ..artifacts.models import EvidenceBundle, InvestigationRequest, PromptPackage
from ._evidence_common import appendix, citations, instructions, render_bullets, summary, unknowns


def build_prompt_package(bundle: EvidenceBundle, request: InvestigationRequest) -> PromptPackage:
    return PromptPackage(
        goal=request.goal_text,
        intent=request.intent_text,
        summary=summary(bundle, request),
        evidence_appendix=appendix(bundle, request),
        unknowns_and_gaps=unknowns(bundle, request),
        instructions=instructions(request),
        citations=citations(bundle),
    )


def render_prompt(bundle: EvidenceBundle, request: InvestigationRequest) -> str:
    package = build_prompt_package(bundle, request)
    if request.format == "text":
        return _render_prompt_text(package)
    return _render_prompt_markdown(package)


def _render_prompt_markdown(package: PromptPackage) -> str:
    lines = ["# DebugOracle Prompt Package", "", "## Goal", package.goal, ""]
    if package.intent:
        lines.extend(["## Intended System State", package.intent, ""])
    lines.extend(["## Summary", package.summary, "", "## Evidence Appendix", package.evidence_appendix, "", "## Unknowns And Gaps"])
    lines.extend([f"- {item}" for item in package.unknowns_and_gaps] or ["- None"])
    lines.extend(["", "## Instructions For ChatGPT", package.instructions, "", "## Citations"])
    lines.extend([f"- {item}" for item in package.citations])
    return "\n".join(lines).rstrip() + "\n"


def _render_prompt_text(package: PromptPackage) -> str:
    sections = ["DebugOracle Prompt Package", "", f"Goal: {package.goal}"]
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
            render_bullets(package.unknowns_and_gaps),
            "",
            "Instructions For ChatGPT:",
            package.instructions,
            "",
            "Citations:",
            render_bullets(package.citations),
        ]
    )
    return "\n".join(sections).rstrip() + "\n"
