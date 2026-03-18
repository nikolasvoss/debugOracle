from __future__ import annotations

import json

from ..artifacts.models import EvidenceBundle
from .report import render_report


def render_snapshot(bundle: EvidenceBundle, fmt: str = "json") -> str:
    if fmt == "json":
        return json.dumps(bundle.to_dict(), indent=2)
    if fmt == "text":
        return render_report(bundle, fmt="text")
    return render_report(bundle, fmt="markdown")
