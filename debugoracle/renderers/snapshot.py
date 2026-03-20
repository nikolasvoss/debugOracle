from __future__ import annotations

import json

from ..artifacts.models import EvidenceBundle


def render_snapshot(
    bundle: EvidenceBundle,
    fmt: str = "json",
    *,
    variable_options=None,
) -> str:
    if fmt != "json":
        raise ValueError("render_snapshot only supports fmt='json'")
    return json.dumps(bundle.to_dict(), indent=2)
