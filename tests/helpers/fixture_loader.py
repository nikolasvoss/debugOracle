from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised when optional dep missing
    yaml = None  # type: ignore[assignment]


def load_fixture_data(path: str | Path) -> tuple[str, str, dict[str, Any]]:
    """Load a replay fixture bundle from tests/fixtures/{name}."""
    fixture_dir = Path(path)
    gdb_path = fixture_dir / "data" / "gdb.log"
    rtt_path = fixture_dir / "data" / "rtt.log"
    metadata_path = fixture_dir / "metadata.yaml"
    mi_text = gdb_path.read_text(encoding="utf-8")
    rtt_text = rtt_path.read_text(encoding="utf-8")
    metadata_text = metadata_path.read_text(encoding="utf-8")
    if yaml is not None:
        metadata = yaml.safe_load(metadata_text)
    else:
        metadata = json.loads(metadata_text)
    if not isinstance(metadata, dict):
        raise ValueError(f"Fixture metadata must be a mapping: {metadata_path}")
    return mi_text, rtt_text, metadata
