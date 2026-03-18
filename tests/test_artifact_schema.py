from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from debugoracle.builder import SnapshotLoadError, build_bundle_from_text, load_bundle, save_bundle
from debugoracle.output import render_report


class ArtifactSchemaTests(unittest.TestCase):
    def test_save_bundle_writes_schema_version_and_live_state(self) -> None:
        bundle = build_bundle_from_text("", "")
        bundle.live_state = {
            "backend": "demo",
            "warnings": ["Synthetic data only."],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_bundle(bundle, str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["live_state"]["backend"], "demo")

    def test_load_bundle_legacy_snapshot_defaults_schema_version_and_renders(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path))
            report = render_report(loaded)

        self.assertEqual(loaded.schema_version, "1")
        self.assertEqual(loaded.live_state, {})
        self.assertIn("DebugOracle Evidence Report", report)

    def test_load_bundle_unknown_schema_version_warns_in_non_strict_mode(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload["schema_version"] = "99"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "future.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path), strict=False)

        self.assertEqual(loaded.schema_version, "99")
        self.assertTrue(
            any("schema version '99'" in warning for warning in loaded.parse_warnings)
        )
        self.assertEqual(
            loaded.provenance["parse_warning_count"],
            len(loaded.parse_warnings),
        )

    def test_load_bundle_unknown_schema_version_fails_in_strict_mode(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload["schema_version"] = "99"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "future.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(SnapshotLoadError):
                load_bundle(str(path), strict=True)

    def test_round_trip_preserves_provenance_and_minimal_live_state(self) -> None:
        bundle = build_bundle_from_text("", "")
        bundle.provenance["custom_note"] = {"source": "fixture", "confidence": 1}
        bundle.live_state = {
            "captured_at": "2026-03-18T10:00:00+00:00",
            "source": "demo",
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_bundle(bundle, str(path))
            loaded = load_bundle(str(path))

        self.assertEqual(loaded.live_state["source"], "demo")
        self.assertEqual(loaded.provenance["custom_note"]["source"], "fixture")


if __name__ == "__main__":
    unittest.main()
