from __future__ import annotations

import dataclasses
from typing import Any

from debugoracle.artifacts.models import InvestigationArtifact

UNSTABLE_FIELDS = {"captured_at", "snapshot_id"}


def comparable(
    artifact: InvestigationArtifact, *, exclude_gdb_events: bool = False
) -> dict[str, Any]:
    """Return a comparison-safe artifact snapshot for deterministic test assertions."""
    data = dataclasses.asdict(artifact)
    for field in UNSTABLE_FIELDS:
        data.pop(field, None)
    if exclude_gdb_events:
        # Known serialisation limitation: SessionEvent payload values are coerced on load.
        sources = data.get("sources")
        if isinstance(sources, dict):
            gdb = sources.get("gdb")
            if isinstance(gdb, dict):
                gdb.pop("events", None)
    return data


def assert_artifacts_equal(
    left: InvestigationArtifact,
    right: InvestigationArtifact,
    *,
    exclude_gdb_events: bool = False,
) -> None:
    """Raise AssertionError when two artifacts differ under deterministic comparison."""
    if comparable(left, exclude_gdb_events=exclude_gdb_events) != comparable(
        right, exclude_gdb_events=exclude_gdb_events
    ):
        raise AssertionError("Artifacts are not equal under comparable() semantics.")
