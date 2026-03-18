from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from debugoracle.artifacts.models import InvestigationRequest
from debugoracle.pipeline.storage import build_artifact_from_sources
from debugoracle.sources.debuggers.gdb.halt_snapshot import build_halt_snapshot
from debugoracle.sources.debuggers.gdb.transcript import parse_gdb_transcript


FIXTURES = Path(__file__).parent / "fixtures"


class PipelineAndRendererTests(unittest.TestCase):
    def test_pipeline_storage_shapes_artifact_from_source_outputs(self) -> None:
        gdb_text = (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        rtt_text = (FIXTURES / "sample.rtt").read_text(encoding="utf-8")
        transcript = parse_gdb_transcript(gdb_text, now_text=lambda: "2026-03-18T10:00:00+00:00")
        halt_snapshot = build_halt_snapshot(
            latest_stop=transcript.latest_stop,
            latest_stack=transcript.latest_stack,
            latest_registers=transcript.latest_registers,
            latest_watched=transcript.latest_watched,
        )

        artifact = build_artifact_from_sources(
            captured_at="2026-03-18T10:00:00+00:00",
            gdb_text=gdb_text,
            rtt_text=rtt_text,
            gdb_source=str(FIXTURES / "sample.mi"),
            rtt_source=str(FIXTURES / "sample.rtt"),
            transcript=transcript,
            halt_snapshot=halt_snapshot,
            rtt_window=40,
        )

        self.assertEqual(artifact.stop_reason, "breakpoint-hit")
        self.assertEqual(artifact.pc, "0x08000100")
        self.assertEqual(artifact.watched_values["system_state"], "READY")
        self.assertEqual(len(artifact.recent_rtt), 3)

    def test_canonical_renderers_produce_expected_outputs(self) -> None:
        from debugoracle.renderers.prompt import render_prompt
        from debugoracle.renderers.report import render_report
        from debugoracle.renderers.snapshot import render_snapshot

        gdb_text = (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        transcript = parse_gdb_transcript(gdb_text, now_text=lambda: "2026-03-18T10:00:00+00:00")
        halt_snapshot = build_halt_snapshot(
            latest_stop=transcript.latest_stop,
            latest_stack=transcript.latest_stack,
            latest_registers=transcript.latest_registers,
            latest_watched=transcript.latest_watched,
        )
        artifact = build_artifact_from_sources(
            captured_at="2026-03-18T10:00:00+00:00",
            gdb_text=gdb_text,
            rtt_text="",
            gdb_source=str(FIXTURES / "sample.mi"),
            rtt_source=None,
            transcript=transcript,
            halt_snapshot=halt_snapshot,
            rtt_window=40,
        )

        request = InvestigationRequest(goal_text="Explain why the target stopped here")

        self.assertIn("DebugOracle Evidence Report", render_report(artifact))
        self.assertIn("DebugOracle Prompt Package", render_prompt(artifact, request))
        self.assertIn('"snapshot_id"', render_snapshot(artifact, fmt="json"))

    def test_canonical_status_renderer_matches_legacy_session_output(self) -> None:
        from debugoracle.renderers.status import render_session_status
        from debugoracle.session import SessionConfig, collect_session_status

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "latest_snapshot.json").write_text("{}", encoding="utf-8")
            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        rendered = render_session_status(status)
        self.assertIn("DebugOracle Session Status", rendered)
        self.assertIn("Snapshot Parse Warnings", rendered)


if __name__ == "__main__":
    unittest.main()
