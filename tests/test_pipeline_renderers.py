from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from debugoracle.artifacts.models import (
    InvestigationArtifact,
    InvestigationRequest,
    VariableEntry,
    VariableEvidence,
)
from debugoracle.pipeline.storage import build_artifact_from_sources
from debugoracle.builder import build_bundle_from_text
from debugoracle.sources.debuggers.gdb.halt_snapshot import build_halt_snapshot
from debugoracle.sources.debuggers.gdb.transcript import parse_gdb_transcript


FIXTURES = Path(__file__).parent / "fixtures"


class PipelineAndRendererTests(unittest.TestCase):
    def test_transcript_accumulates_variable_entries_across_multiple_result_records(self) -> None:
        transcript = parse_gdb_transcript(
            "\n".join(
                [
                    '^done,locals=[{name="a",value="1"}]',
                    '^done,locals=[{name="b",value="2"}]',
                    '^done,variables=[{name="x",value="3"}]',
                    '^done,variables=[{name="y",value="4"}]',
                ]
            ),
            now_text=lambda: "2026-03-18T10:00:00+00:00",
        )

        self.assertEqual([entry.name for entry in transcript.variable_evidence.locals], ["a", "b"])
        self.assertEqual([entry.name for entry in transcript.variable_evidence.unknown], ["x", "y"])

    def test_transcript_and_report_preserve_array_and_struct_values(self) -> None:
        from debugoracle.renderers.report import render_report

        transcript = parse_gdb_transcript(
            "\n".join(
                [
                    '*stopped,reason="breakpoint-hit",frame={addr="0x08000100",func="main",file="main.c",fullname="/workspace/src/main.c",line="42"}',
                    '^done,locals=['
                    '{name="arr",value="{1, 2, 3, 4}"},'
                    '{name="point",value="{x = 1, y = 2}"},'
                    '{name="matrix",value="{{1, 2}, {3, 4}}"},'
                    '{name="message",value="[72, 101, 108, 108, 111]"}'
                    ']',
                ]
            ),
            now_text=lambda: "2026-03-18T10:00:00+00:00",
        )

        self.assertEqual(
            [entry.value for entry in transcript.variable_evidence.locals],
            [
                "{1, 2, 3, 4}",
                "{x = 1, y = 2}",
                "{{1, 2}, {3, 4}}",
                "[72, 101, 108, 108, 111]",
            ],
        )

        artifact = InvestigationArtifact(
            snapshot_id="snap-composite",
            captured_at="2026-03-18T10:00:00+00:00",
            stop_reason="breakpoint-hit",
            pc="0x08000100",
            lr="0x08000081",
            sp="0x20002000",
            variable_evidence=transcript.variable_evidence,
        )

        report = render_report(artifact)

        self.assertIn("arr: {1, 2, 3, 4}", report)
        self.assertIn("point: {x = 1, y = 2}", report)
        self.assertIn("matrix: {{1, 2}, {3, 4}}", report)
        self.assertIn("message: [72, 101, 108, 108, 111]", report)

    def test_pipeline_storage_shapes_artifact_from_source_outputs(self) -> None:
        gdb_text = (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        rtt_text = (FIXTURES / "sample.rtt").read_text(encoding="utf-8")
        transcript = parse_gdb_transcript(gdb_text, now_text=lambda: "2026-03-18T10:00:00+00:00")
        halt_snapshot = build_halt_snapshot(
            latest_stop=transcript.latest_stop,
            latest_stack=transcript.latest_stack,
            latest_registers=transcript.latest_registers,
            variable_evidence=transcript.variable_evidence,
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
        self.assertEqual(artifact.variable_evidence.locals[0].name, "system_state")
        self.assertEqual(artifact.variable_evidence.locals[0].value, "READY")
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
            variable_evidence=transcript.variable_evidence,
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

        rendered_report = render_report(artifact)
        self.assertIn("DebugOracle Evidence Report", rendered_report)
        self.assertIn("Current State:", rendered_report)
        self.assertIn("DebugOracle Prompt Package", render_prompt(artifact, request))
        self.assertIn('"snapshot_id"', render_snapshot(artifact, fmt="json"))

    def test_partial_snapshot_marks_missing_rtt_source_absent_and_report_rtt_fails(self) -> None:
        from debugoracle.renderers.report import ReportRenderOptions, render_report

        bundle = build_bundle_from_text((FIXTURES / "sample.mi").read_text(encoding="utf-8"), "")

        self.assertTrue(bundle.has_embedded_gdb_source)
        self.assertFalse(bundle.has_embedded_rtt_source)
        with self.assertRaisesRegex(RuntimeError, "embedded rtt source"):
            render_report(bundle, options=ReportRenderOptions(include_rtt=True))

    def test_partial_snapshot_marks_missing_gdb_source_absent_and_report_gdb_fails(self) -> None:
        from debugoracle.renderers.report import ReportRenderOptions, render_report

        bundle = build_bundle_from_text("", (FIXTURES / "sample.rtt").read_text(encoding="utf-8"))

        self.assertFalse(bundle.has_embedded_gdb_source)
        self.assertTrue(bundle.has_embedded_rtt_source)
        with self.assertRaisesRegex(RuntimeError, "embedded gdb source"):
            render_report(bundle, options=ReportRenderOptions(include_gdb=True))

    def test_render_snapshot_rejects_non_json_formats(self) -> None:
        from debugoracle.renderers.snapshot import render_snapshot

        artifact = InvestigationArtifact(
            snapshot_id="snap-123",
            captured_at="2026-03-18T10:00:00+00:00",
            stop_reason=None,
            pc=None,
            lr=None,
            sp=None,
        )

        with self.assertRaisesRegex(ValueError, "only supports"):
            render_snapshot(artifact, fmt="text")

    def test_report_renders_bucketed_variable_summary_with_caps_and_unknowns(self) -> None:
        from debugoracle.renderers.report import render_report

        artifact = InvestigationArtifact(
            snapshot_id="snap-123",
            captured_at="2026-03-18T10:00:00+00:00",
            stop_reason="breakpoint-hit",
            pc="0x08000100",
            lr="0x08000081",
            sp="0x20002000",
            variable_evidence=VariableEvidence(
                locals=[
                    VariableEntry(name=f"local_{index}", value=str(index), bucket="locals", order=index)
                    for index in range(6)
                ],
                globals=[
                    VariableEntry(name="system_state", value="READY", bucket="globals", order=10),
                ],
                watchpoints=[
                    VariableEntry(name="watch_counter", value="9", bucket="watchpoints", order=11),
                ],
                unknown=[
                    VariableEntry(name="mystery", value="??", bucket="unknown", order=12),
                ],
            ),
        )

        report = render_report(artifact)

        self.assertIn("Variable Summary:", report)
        self.assertIn("- Locals: 6 total", report)
        self.assertIn("local_0: 0", report)
        self.assertIn("local_4: 4", report)
        self.assertNotIn("local_5: 5", report)
        self.assertIn("... 1 more omitted", report)
        self.assertIn("- Globals: 1 total", report)
        self.assertIn("system_state: READY", report)
        self.assertIn("- Watchpoints: 1 total", report)
        self.assertIn("watch_counter: 9", report)
        self.assertIn("- Unknown Classification: 1 total", report)
        self.assertIn("mystery: ??", report)

    def test_canonical_status_renderer_surfaces_action_first_output(self) -> None:
        from debugoracle.renderers.status import render_session_status
        from debugoracle.session import SessionConfig, collect_session_status

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "latest_snapshot.json").write_text("{}", encoding="utf-8")
            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        rendered = render_session_status(status)
        self.assertIn("DebugOracle Session Status", rendered)
        self.assertIn("Current State:", rendered)
        self.assertIn("Next Useful Command:", rendered)


if __name__ == "__main__":
    unittest.main()
