from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .halted_analysis import HaltPolicyDecision


@dataclass(frozen=True)
class TrustDecision:
    verdict: str
    summary: str
    reasons: list[str] = field(default_factory=list)
    recommended_action: str = "dbgoracle fetch --workspace-root ."

    @property
    def allow_full_report_by_default(self) -> bool:
        return self.verdict != "unsafe"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_artifact_trust(
    *,
    snapshot_exists: bool,
    snapshot_usable: bool,
    snapshot_stale: bool,
    action_state: str,
    action_reason: str,
    recommended_next_command: str,
    halt_policy: HaltPolicyDecision | None = None,
    critical_warnings: list[str] | None = None,
    parse_warnings: list[str] | None = None,
    variable_count: int | None = None,
    has_embedded_gdb_source: bool | None = None,
) -> TrustDecision:
    reasons: list[str] = []
    critical_warnings = list(critical_warnings or [])
    parse_warnings = list(parse_warnings or [])

    if not snapshot_exists:
        reasons.append("No reusable snapshot is available.")
        return TrustDecision(
            verdict="unsafe",
            summary="Current workspace evidence is not safe for grounded reasoning.",
            reasons=reasons,
            recommended_action=recommended_next_command,
        )

    if halt_policy is not None and not halt_policy.allowed:
        reasons.extend(halt_policy.warnings)

    if action_state == "refresh_recommended":
        reasons.append("Raw evidence is newer than the snapshot.")

    reasons.extend(critical_warnings)

    if not snapshot_usable:
        if action_reason and action_reason not in reasons:
            reasons.append(action_reason)
        if not reasons and parse_warnings:
            reasons.append(parse_warnings[0])
        return TrustDecision(
            verdict="unsafe",
            summary="This report is not safe for grounded reasoning.",
            reasons=reasons or ["Snapshot evidence is not usable."],
            recommended_action=recommended_next_command,
        )

    caution_reasons: list[str] = []
    if snapshot_stale:
        caution_reasons.append("Snapshot file is stale.")
    if variable_count == 0:
        caution_reasons.append("No variable evidence was captured in the snapshot.")
    if has_embedded_gdb_source is False:
        caution_reasons.append("GDB source evidence is missing from the snapshot.")
    for warning in parse_warnings:
        lowered = warning.lower()
        if (
            "evidence quality is reduced" in lowered
            or "could not parse snapshot" in lowered
        ):
            caution_reasons.append(warning)

    if reasons:
        return TrustDecision(
            verdict="unsafe",
            summary="This report is not safe for grounded reasoning.",
            reasons=reasons,
            recommended_action=recommended_next_command,
        )

    if caution_reasons:
        return TrustDecision(
            verdict="caution",
            summary="This report is usable with caution.",
            reasons=caution_reasons,
            recommended_action=recommended_next_command,
        )

    return TrustDecision(
        verdict="safe",
        summary="This report is safe for grounded reasoning.",
        reasons=["Snapshot evidence is current enough and usable for inspection."],
        recommended_action=recommended_next_command,
    )
