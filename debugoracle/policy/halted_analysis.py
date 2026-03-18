from __future__ import annotations

from dataclasses import dataclass, field

HALT_REQUIRED_TARGET_STATES = {"running", "unknown", "unavailable"}


@dataclass(frozen=True)
class HaltPolicyDecision:
    allowed: bool
    target_state: str
    warnings: list[str] = field(default_factory=list)


def evaluate_halt_requirement(target_state: str | None) -> HaltPolicyDecision:
    normalized = (target_state or "unknown").strip().lower() or "unknown"
    if normalized not in HALT_REQUIRED_TARGET_STATES:
        return HaltPolicyDecision(allowed=True, target_state=normalized)
    return HaltPolicyDecision(
        allowed=False,
        target_state=normalized,
        warnings=[
            "Halted analysis is required before reading live registers or memory.",
            f"Target state '{normalized}' is not safe for correlated live reads.",
        ],
    )


def evaluate_artifact_live_state(live_state: object) -> HaltPolicyDecision:
    if not isinstance(live_state, dict):
        return HaltPolicyDecision(allowed=True, target_state="unspecified")
    if "target_state" not in live_state:
        return HaltPolicyDecision(allowed=True, target_state="unspecified")
    return evaluate_halt_requirement(live_state.get("target_state"))
