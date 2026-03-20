from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from debugoracle.artifacts.models import CURRENT_BUNDLE_SCHEMA_VERSION, EvidenceBundle, VariableEntry
from debugoracle.renderers.report import ReportRenderOptions, render_report
from debugoracle.builder import SnapshotLoadError, build_bundle_from_text, load_bundle, save_bundle


class ArtifactSchemaTests(unittest.TestCase):
    def test_canonical_artifact_api_supports_round_trip_without_legacy_bundle_names(self) -> None:
        from debugoracle.artifacts.models import InvestigationArtifact
        from debugoracle.artifacts.repository import load_artifact, save_artifact

        artifact = build_bundle_from_text("", "")
        artifact.live_state = {"source": "canonical-artifact"}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.json"
            save_artifact(artifact, str(path))
            loaded = load_artifact(str(path))

        self.assertIs(InvestigationArtifact, type(artifact))
        self.assertIsInstance(loaded, InvestigationArtifact)
        self.assertEqual(loaded.live_state["source"], "canonical-artifact")

    def test_builder_compatibility_exports_match_canonical_artifact_boundary(self) -> None:
        from debugoracle.artifacts.bundle import load_bundle as canonical_load_bundle
        from debugoracle.artifacts.bundle import save_bundle as canonical_save_bundle
        from debugoracle.artifacts.models import (
            CURRENT_BUNDLE_SCHEMA_VERSION as canonical_schema_version,
        )
        from debugoracle.artifacts.models import EvidenceBundle as CanonicalEvidenceBundle
        from debugoracle.artifacts.models import InvestigationArtifact

        bundle = build_bundle_from_text("", "")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_bundle(bundle, str(path))
            loaded = load_bundle(str(path))

        self.assertIs(EvidenceBundle, CanonicalEvidenceBundle)
        self.assertIs(CanonicalEvidenceBundle, InvestigationArtifact)
        self.assertIs(load_bundle, canonical_load_bundle)
        self.assertIs(save_bundle, canonical_save_bundle)
        self.assertEqual(CURRENT_BUNDLE_SCHEMA_VERSION, canonical_schema_version)
        self.assertIsInstance(loaded, CanonicalEvidenceBundle)

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

        self.assertEqual(payload["schema_version"], CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(payload["live_state"]["backend"], "demo")

    def test_save_and_load_preserve_structured_variable_evidence(self) -> None:
        bundle = build_bundle_from_text("", "")
        bundle.variable_evidence.locals.append(
            VariableEntry(
                name="system_state",
                value="READY",
                bucket="locals",
                origin="fixture",
                order=0,
            )
        )
        bundle.variable_evidence.unknown.append(
            VariableEntry(
                name="dup",
                value="shadow",
                bucket="unknown",
                origin="fixture",
                order=1,
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_bundle(bundle, str(path))
            loaded = load_bundle(str(path))

        self.assertEqual(loaded.schema_version, CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(loaded.variable_evidence.locals[0].name, "system_state")
        self.assertEqual(loaded.variable_evidence.locals[0].value, "READY")
        self.assertEqual(loaded.variable_evidence.unknown[0].name, "dup")

    def test_save_and_load_round_trip_embeds_sources_object(self) -> None:
        bundle = build_bundle_from_text("^done\n", "line one\nline two\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_bundle(bundle, str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_bundle(str(path))

        self.assertEqual(payload["schema_version"], CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertIn("sources", payload)
        self.assertEqual(payload["sources"]["gdb"]["raw_text"], "^done\n")
        self.assertEqual(payload["sources"]["gdb"]["event_count"], len(payload["sources"]["gdb"]["events"]))
        self.assertEqual(payload["sources"]["rtt"]["raw_text"], "line one\nline two\n")
        self.assertEqual(payload["sources"]["rtt"]["lines"], ["line one", "line two"])
        self.assertEqual(payload["sources"]["rtt"]["line_count"], 2)
        self.assertEqual(loaded.sources.gdb.raw_text, "^done\n")
        self.assertEqual(loaded.sources.rtt.lines, ["line one", "line two"])

    def test_load_bundle_legacy_snapshot_defaults_schema_version_and_renders(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path))
            report = render_report(loaded)

        self.assertEqual(loaded.schema_version, CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(loaded.live_state, {})
        self.assertIn("DebugOracle Evidence Report", report)

    def test_load_bundle_legacy_snapshot_exposes_best_effort_sources_without_claiming_embedding(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)
        payload.pop("sources", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path))

        self.assertFalse(loaded.has_embedded_gdb_source)
        self.assertFalse(loaded.has_embedded_rtt_source)
        self.assertIsNone(loaded.sources.gdb.raw_text)
        self.assertIsNone(loaded.sources.rtt.raw_text)
        self.assertEqual(loaded.sources.gdb.event_count, len(loaded.session_events))
        self.assertEqual(loaded.sources.rtt.lines, loaded.recent_rtt)

    def test_legacy_snapshot_rejects_embedded_gdb_inspection_with_clear_error(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)
        payload.pop("sources", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path))

        with self.assertRaisesRegex(RuntimeError, "embedded gdb source"):
            render_report(loaded, options=ReportRenderOptions(include_gdb=True))

    def test_legacy_snapshot_rejects_embedded_rtt_inspection_with_clear_error(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)
        payload.pop("sources", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path))

        with self.assertRaisesRegex(RuntimeError, "embedded rtt source"):
            render_report(loaded, options=ReportRenderOptions(include_rtt=True))

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

    def test_canonical_repository_preserves_strict_schema_checks(self) -> None:
        from debugoracle.artifacts.repository import ArtifactLoadError, load_artifact

        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload["schema_version"] = "99"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "future.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArtifactLoadError):
                load_artifact(str(path), strict=True)

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
