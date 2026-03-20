from __future__ import annotations

import json
import os
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from debugoracle.artifacts.models import CURRENT_BUNDLE_SCHEMA_VERSION, EvidenceBundle, VariableEntry
from debugoracle.renderers.report import ReportRenderOptions, render_report
from debugoracle.builder import SnapshotLoadError, build_bundle_from_text, load_bundle, save_bundle


FIXTURES = Path(__file__).parent / "fixtures"


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

    def test_builder_defaults_to_catalog_only_register_embedding(self) -> None:
        bundle = build_bundle_from_text(
            '*stopped,reason="breakpoint-hit"\n^done\n',
            'line one\n',
            svd_file_path=str(FIXTURES / "sample.svd"),
        )

        self.assertTrue(bundle.has_embedded_register_source)
        self.assertEqual(bundle.sources.registers.success_count, 0)
        self.assertEqual(bundle.sources.registers.failure_count, 0)
        self.assertEqual(bundle.provenance["register_capture_mode"], "catalog")

    def test_save_and_load_round_trip_embeds_register_sources_object(self) -> None:
        with _FakeOpenOcdServer(values={0x48000000: "0xaaaaaaaa", 0x48000010: "0x00000001"}) as server:
            with patch.dict(
                os.environ,
                {
                    "DEBUGORACLE_OPENOCD_HOST": server.host,
                    "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                },
                clear=False,
            ):
                bundle = build_bundle_from_text(
                    "*stopped,reason=\"breakpoint-hit\"\n^done\n",
                    "line one\n",
                    svd_file_path=str(FIXTURES / "sample.svd"),
                    enable_live_peripheral_capture=True,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_bundle(bundle, str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_bundle(str(path))

        self.assertIn("registers", payload["sources"])
        self.assertEqual(payload["sources"]["registers"]["device_name"], "STM32L432KCTest")
        self.assertEqual(payload["sources"]["registers"]["register_count"], 4)
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)
        self.assertEqual(payload["sources"]["registers"]["skipped_count"], 2)
        self.assertEqual(payload["provenance"]["register_capture_mode"], "live")
        self.assertTrue(loaded.has_embedded_register_source)
        self.assertEqual(loaded.sources.registers.peripherals[0].name, "GPIOA")

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

    def test_legacy_snapshot_rejects_embedded_register_inspection_with_clear_error(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)
        payload.pop("sources", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_bundle(str(path))

        with self.assertRaisesRegex(RuntimeError, "embedded register source"):
            render_report(loaded, options=ReportRenderOptions(regs_list_selector=""))

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


class _FakeOpenOcdHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        buffer = b""
        while True:
            chunk = self.request.recv(1024)
            if not chunk:
                return
            buffer += chunk
            while b"\x1a" in buffer:
                raw_command, buffer = buffer.split(b"\x1a", 1)
                command = raw_command.decode("utf-8", errors="replace").strip()
                response = self.server.build_response(command)
                self.request.sendall(response.encode("utf-8") + b"\x1a")


class _FakeOpenOcdServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, *, values: dict[int, str]) -> None:
        super().__init__(("127.0.0.1", 0), _FakeOpenOcdHandler)
        self._values = values
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        return str(self.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def __enter__(self) -> "_FakeOpenOcdServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=1)

    def build_response(self, command: str) -> str:
        parts = command.split()
        if len(parts) != 4 or parts[0] != "read_memory":
            return "unsupported-command"
        address = int(parts[1], 0)
        count = int(parts[3], 0)
        if count != 1 or address not in self._values:
            return "error"
        return self._values[address]


if __name__ == "__main__":
    unittest.main()
