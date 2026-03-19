from __future__ import annotations

import json

from ..artifacts.models import EvidenceBundle
from ._evidence_common import VariableRenderOptions
from .report import render_report


def render_snapshot(
    bundle: EvidenceBundle,
    fmt: str = "json",
    *,
    variable_options: VariableRenderOptions | None = None,
) -> str:
    if fmt == "json":
        return json.dumps(bundle.to_dict(), indent=2)
    if fmt == "text":
        return render_report(bundle, fmt="text", variable_options=variable_options)
    return render_report(bundle, fmt="markdown", variable_options=variable_options)
