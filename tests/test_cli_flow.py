from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.rtt import RttCaptureState
from debugoracle.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


class DebugOracleCliTests(unittest.TestCase):
    def test_snapshot_json_contains_expected_bundle_fields(self) -> None:
        output = self._run_cli(
            [
                "snapshot",
                "--gdb-mi",
                str(FIXTURES / "sample.mi"),
                "--rtt",
                str(FIXTURES / "sample.rtt"),
            ]
        )
        payload = json.loads(output)
        self.assertEqual(payload["stop_reason"], "breakpoint-hit")
        self.assertEqual(payload["pc"], "0x08000100")
        self.assertEqual(payload["watched_values"]["system_state"], "READY")
        self.assertEqual(len(payload["recent_rtt"]), 3)

    def test_snapshot_classifies_noise_lines_without_masking_stop_context(self) -> None:
        noisy_log = (
            "(gdb)\n"
            '@"Unable to match requested speed 500 kHz, using 480 kHz\\n"\n'
            "17+download,{section=\".isr_vector\",section-size=\"400\",total-size=\"800\"}\n"
            "@\"rtt: Listening\\n\"\n"
            "random-non-mi-line\n"
            + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            noisy_path = Path(tmpdir) / "noisy.mi"
            noisy_path.write_text(noisy_log, encoding="utf-8")
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(noisy_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)
            counts = payload["provenance"]["parse_event_counts"]
            severity_counts = payload["provenance"]["parse_event_severity_counts"]

        self.assertEqual(payload["stop_reason"], "breakpoint-hit")
        self.assertEqual(payload["pc"], "0x08000100")
        self.assertEqual(counts.get("prompt-marker"), 1)
        self.assertEqual(counts.get("console-output", 0), 2)
        self.assertNotIn("mi-parse-error-known", counts)
        self.assertNotIn("mi-parse-error-unhandled", counts)
        self.assertEqual(counts.get("non_mi_line", 0), 1)
        self.assertEqual(payload["provenance"]["non_mi_line_count"], 4)
        self.assertEqual(payload["provenance"]["mi_parse_error_count"], 0)
        self.assertEqual(severity_counts.get("warn", 0), 0)
        self.assertGreaterEqual(severity_counts.get("info", 0), 8)

    def test_report_summary_prefers_actionable_metrics_over_raw_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            noisy_log = (
                "(gdb)\n"
                '@"Unable to match requested speed 500 kHz, using 480 kHz\\n"\n'
                "17+download,{section=\".isr_vector\",section-size=\"400\",total-size=\"800\"}\n"
                "@\"rtt: Listening\\n\"\n"
                + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
            )
            noisy_path = Path(tmpdir) / "noisy.mi"
            noisy_path.write_text(noisy_log, encoding="utf-8")
            snapshot_path = Path(tmpdir) / "snapshot.json"
            self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(noisy_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            report_output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        self.assertIn("Parsing Summary", report_output)
        self.assertIn("Evidence Quality Score", report_output)
        self.assertIn("Top non-MI patterns", report_output)
        self.assertIn("Event types:", report_output)
        self.assertIn("Raw Non-MI Excerpt", report_output)

    def test_snapshot_compacts_noise_into_summary_warning(self) -> None:
        noisy_log = (
            "(gdb)\n"
            + ('@"Unable to match requested speed 500 kHz, using 480 kHz\\n"\n' * 8)
            + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            noisy_path = Path(tmpdir) / "noisy.mi"
            noisy_path.write_text(noisy_log, encoding="utf-8")
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(noisy_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)

        self.assertEqual(payload["stop_reason"], "breakpoint-hit")
        self.assertEqual(payload["provenance"]["parse_warning_count"], 1)
        self.assertEqual(payload["provenance"]["parse_event_counts"]["prompt-marker"], 1)
        self.assertEqual(payload["provenance"]["parse_event_counts"]["console-output"], 8)
        self.assertIn("non_mi_pattern_counts", payload["provenance"])
        self.assertNotIn("non_mi_patterns", payload["provenance"])
        top_pattern = payload["provenance"]["non_mi_pattern_counts"][0]
        self.assertEqual(
            top_pattern["pattern"],
            "Unable to match requested speed 500 kHz, using 480 kHz\\n",
        )
        self.assertEqual(top_pattern["count"], 8)

    def test_report_raw_non_mi_excerpt_is_compacted(self) -> None:
        noisy_log = (
            '@"Unable to match requested speed 500 kHz, using 480 kHz\\n"\n' * 10
            + "(gdb)\n" * 3
            + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            noisy_path = Path(tmpdir) / "noisy.mi"
            noisy_path.write_text(noisy_log, encoding="utf-8")
            snapshot_path = Path(tmpdir) / "snapshot.json"
            self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(noisy_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            report_output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        raw_section = report_output.split("## Raw Non-MI Excerpt", 1)[1]
        raw_section = raw_section.split("## Unknowns And Gaps", 1)[0]
        self.assertIn("Top non-MI patterns", raw_section)
        self.assertLessEqual(
            raw_section.count("Unable to match requested speed 500 kHz, using 480 kHz"),
            2,
        )
        self.assertIn("(repeated 10 times)", raw_section)
        self.assertNotIn("x10", raw_section)
        self.assertIn("(gdb)", raw_section)

    def test_report_sanitizes_control_characters_in_non_mi_patterns(self) -> None:
        noisy_log = (
            '(gdb)\n'
            '@"first line\\nsecond line\\tindent\\rreturn\\n"\n'
            '@"first line\\nsecond line\\tindent\\rreturn\\n"\n'
            + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            noisy_path = Path(tmpdir) / "control.mi"
            noisy_path.write_text(noisy_log, encoding="utf-8")
            snapshot_path = Path(tmpdir) / "snapshot.json"
            self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(noisy_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            report_output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertIn("first line\\nsecond line\\tindent\\rreturn\\n", report_output)
        self.assertIn("(repeated 2 times)", report_output)
        self.assertNotIn("first line\nsecond line", report_output)
        self.assertEqual(
            payload["provenance"]["non_mi_pattern_counts"][0]["pattern"],
            "first line\\nsecond line\\tindent\\rreturn\\n",
        )

    def test_report_handles_snapshots_missing_non_mi_pattern_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            payload["provenance"].pop("non_mi_pattern_counts", None)
            snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
            report_output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        self.assertNotIn("Top non-MI patterns", report_output)
        self.assertIn("## Parsing Summary", report_output)
        self.assertIn("DebugOracle Evidence Report", report_output)

    def test_prompt_markdown_contains_goal_intent_and_citations(self) -> None:
        output = self._run_cli(
            [
                "prompt",
                "--gdb-mi",
                str(FIXTURES / "sample.mi"),
                "--rtt",
                str(FIXTURES / "sample.rtt"),
                "--goal",
                "Does the current system state match boot completion?",
                "--intent",
                "The firmware should be in READY state after initialization.",
            ]
        )
        self.assertIn("# DebugOracle Prompt Package", output)
        self.assertIn("Does the current system state match boot completion?", output)
        self.assertIn("The firmware should be in READY state after initialization.", output)
        self.assertIn("Instructions For ChatGPT", output)
        self.assertIn("C1 Session context and stop state", output)

    def test_observe_writes_snapshot_reused_by_report_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            observe_output = self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            self.assertTrue(snapshot_path.exists())
            report_output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])
            prompt_output = self._run_cli(
                [
                    "prompt",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--goal",
                    "Explain why the target stopped here",
                ]
            )
        self.assertIn("Saved snapshot", observe_output)
        self.assertIn("DebugOracle Evidence Report", report_output)
        self.assertIn("Snapshot ID", report_output)
        self.assertIn("Recent RTT", report_output)
        self.assertIn("# DebugOracle Prompt Package", prompt_output)
        self.assertIn("Explain why the target stopped here", prompt_output)

    def test_observe_defaults_to_workspace_session_folder_for_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir(parents=True)
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            cwd = Path(tmpdir) / "other"
            cwd.mkdir()
            previous = os.getcwd()
            try:
                os.chdir(cwd)
                observe_output = self._run_cli(
                    [
                        "observe",
                        "--workspace-root", str(workspace),
                        "--gdb-mi", ".dbgoracle/cortex-debug-shared-mi.log",
                        "--rtt", ".dbgoracle/session.rtt",
                    ]
                )
            finally:
                os.chdir(previous)

            snapshot_path = session_dir / "latest_snapshot.json"
            self.assertTrue(snapshot_path.exists())
            self.assertIn(f"Saved snapshot", observe_output)
            self.assertIn(str(snapshot_path), observe_output)
            status_output = self._run_cli(["status", "--workspace-root", str(workspace)])
            self.assertIn("Health: healthy", status_output)
            self.assertIn("Snapshot ID: snap-", status_output)
            self.assertNotIn("Snapshot file not found", status_output)

    def test_snapshot_uses_auto_discovery_in_current_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            auto_bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            auto_snapshot = session_dir / "latest_snapshot.json"
            save_bundle(auto_bundle, str(auto_snapshot))

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output, stderr = self._run_cli(
                    ["snapshot", "--format", "json"],
                    capture_stderr=True,
                )
            finally:
                os.chdir(previous)

            payload = json.loads(output)
            self.assertEqual(payload["snapshot_id"], auto_bundle.snapshot_id)
            self.assertIn("Auto-discovered input paths for snapshot:", stderr)
            self.assertIn(f"- snapshot-file: {auto_snapshot}", stderr)

    def test_snapshot_prefers_workspace_root_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            auto_bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output, stderr = self._run_cli(
                    ["snapshot", "--format", "json"],
                    capture_stderr=True,
                )
            finally:
                os.chdir(previous)

            payload = json.loads(output)
            self.assertEqual(payload["snapshot_id"], auto_bundle.snapshot_id)
            self.assertIn("Auto-discovered input paths for snapshot:", stderr)
            self.assertIn(f"- gdb-mi: {workspace / 'cortex-debug-shared-mi.log'}", stderr)
            self.assertIn(f"- rtt: {workspace / 'session.rtt'}", stderr)

    def test_prompt_uses_auto_discovery_in_current_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            save_bundle(bundle, str(session_dir / "latest_snapshot.json"))

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output, _ = self._run_cli(
                    [
                        "prompt",
                        "--goal",
                        "Explain why the target stopped here",
                    ],
                    capture_stderr=True,
                )
            finally:
                os.chdir(previous)

        self.assertIn("Snapshot ID:", output)
        self.assertIn(bundle.snapshot_id, output)

    def test_prompt_prefers_workspace_root_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            save_bundle(bundle, str(workspace / "latest_snapshot.json"))

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output = self._run_cli(
                    [
                        "prompt",
                        "--goal",
                        "Explain why the target stopped here",
                    ]
                )
            finally:
                os.chdir(previous)

        self.assertIn("Snapshot ID:", output)
        self.assertIn(bundle.snapshot_id, output)

    def test_snapshot_prefers_explicit_snapshot_file_over_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            discovered_bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            explicit_mi = Path(tmpdir) / "explicit.mi"
            explicit_mi.write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8") + "\n# explicit capture marker\n",
                encoding="utf-8",
            )
            explicit_bundle = build_bundle_from_files(str(explicit_mi), str(FIXTURES / "sample.rtt"))
            discovered_snapshot = session_dir / "latest_snapshot.json"
            explicit_snapshot = workspace / "explicit_snapshot.json"

            save_bundle(discovered_bundle, str(discovered_snapshot))
            save_bundle(explicit_bundle, str(explicit_snapshot))

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output = self._run_cli(
                    [
                        "snapshot",
                        "--snapshot-file",
                        str(explicit_snapshot),
                        "--format",
                        "json",
                    ]
                )
            finally:
                os.chdir(previous)

        payload = json.loads(output)
        self.assertEqual(payload["snapshot_id"], explicit_bundle.snapshot_id)
        self.assertNotEqual(payload["snapshot_id"], discovered_bundle.snapshot_id)

    def test_observe_uses_discovered_workspace_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output, stderr = self._run_cli(
                    ["observe"],
                    capture_stderr=True,
                )
            finally:
                os.chdir(previous)

            snapshot_path = session_dir / "latest_snapshot.json"
            self.assertIn("Saved snapshot", output)
            self.assertIn(f"{snapshot_path}", output)
            self.assertTrue(snapshot_path.exists())
            self.assertIn("Auto-discovered input paths for observe:", stderr)

    def test_observe_prefers_workspace_root_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                output, stderr = self._run_cli(
                    ["observe"],
                    capture_stderr=True,
                )
            finally:
                os.chdir(previous)

            snapshot_path = workspace / "latest_snapshot.json"
            self.assertIn("Saved snapshot", output)
            self.assertIn(f"{snapshot_path}", output)
            self.assertIn("- gdb-mi: " + str(workspace / "cortex-debug-shared-mi.log"), stderr)
            self.assertIn("- rtt: " + str(workspace / "session.rtt"), stderr)
            self.assertTrue(snapshot_path.exists())

    def test_snapshot_fails_with_clear_message_when_nothing_can_be_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            previous = os.getcwd()
            try:
                os.chdir(workspace)
                with self.assertRaises(SystemExit) as error:
                    self._run_cli(["snapshot"])
            finally:
                os.chdir(previous)

        message = str(error.exception)
        self.assertIn("could not auto-resolve an input source", message)
        self.assertIn(".dbgoracle/latest_snapshot.json", message)
        self.assertIn(".dbgoracle/cortex-debug-shared-mi.log", message)

    def test_snapshot_can_run_with_only_rtt_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            rtt_path = workspace / "session.rtt"
            rtt_path.write_text((FIXTURES / "sample.rtt").read_text(encoding="utf-8"), encoding="utf-8")

            output = self._run_cli(
                [
                    "snapshot",
                    "--workspace-root",
                    str(workspace),
                    "--rtt",
                    str(rtt_path),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)

        self.assertIn("No GDB/MI input was provided before building this snapshot.", " ".join(payload["parse_warnings"]))
        self.assertEqual(payload["provenance"]["gdb_mi_source"], "<missing-gdb-mi>")

    def test_observe_can_run_with_only_rtt_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            rtt_path = workspace / "session.rtt"
            rtt_path.write_text((FIXTURES / "sample.rtt").read_text(encoding="utf-8"), encoding="utf-8")
            snapshot_path = workspace / "snapshot.json"

            output = self._run_cli(
                [
                    "observe",
                    "--workspace-root",
                    str(workspace),
                    "--rtt",
                    str(rtt_path),
                    "--state-out",
                    str(snapshot_path),
                ]
            )

            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertIn("Saved snapshot", output)
        self.assertIn("snapshot_id", payload)
        self.assertIn("No GDB/MI input was provided before building this snapshot.", " ".join(payload["parse_warnings"]))

    def test_prompt_can_run_with_only_rtt_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            rtt_path = workspace / "session.rtt"
            rtt_path.write_text((FIXTURES / "sample.rtt").read_text(encoding="utf-8"), encoding="utf-8")
            output = self._run_cli(
                [
                    "prompt",
                    "--workspace-root",
                    str(workspace),
                    "--rtt",
                    str(rtt_path),
                    "--goal",
                    "Summarize what this trace indicates.",
                ]
            )

        self.assertIn("# DebugOracle Prompt Package", output)
        self.assertIn("Summarize what this trace indicates.", output)

    def test_observe_writes_snapshot_next_to_explicit_inputs_when_no_state_out_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            logs = workspace / "custom-logs"
            logs.mkdir()
            gdb = logs / "cortex-debug-shared-mi.log"
            rtt = logs / "session.rtt"
            gdb.write_text((FIXTURES / "sample.mi").read_text(encoding="utf-8"), encoding="utf-8")
            rtt.write_text((FIXTURES / "sample.rtt").read_text(encoding="utf-8"), encoding="utf-8")

            observe_output = self._run_cli(
                [
                    "observe",
                    "--workspace-root", str(workspace),
                    "--gdb-mi", str(gdb),
                    "--rtt", str(rtt),
                ]
            )

            inferred_snapshot = logs / "latest_snapshot.json"
            fallback_snapshot = workspace / ".dbgoracle" / "latest_snapshot.json"
            self.assertTrue(inferred_snapshot.exists())
            self.assertFalse(fallback_snapshot.exists())
            self.assertIn(f"Saved snapshot", observe_output)
            self.assertIn(str(inferred_snapshot), observe_output)

    def test_observe_warns_when_rtt_capture_connected_but_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            gdb = session_dir / "cortex-debug-shared-mi.log"
            rtt = session_dir / "session.rtt"
            state = session_dir / "session.rtt.state.json"
            gdb.write_text((FIXTURES / "sample.mi").read_text(encoding="utf-8"), encoding="utf-8")
            rtt.write_text("", encoding="utf-8")
            state.write_text(
                json.dumps(
                    RttCaptureState(
                        source="openocd-rtt-tcp",
                        host="127.0.0.1",
                        port=60001,
                        status="connected",
                        connected_at="2026-03-16T10:00:00+00:00",
                        last_byte_at=None,
                        bytes_captured=0,
                        error=None,
                    ).to_dict(),
                    indent=2,
                ),
                encoding="utf-8",
            )

            observe_output = self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(gdb),
                    "--rtt",
                    str(rtt),
                    "--state-out",
                    str(session_dir / "snapshot.json"),
                ]
            )

        self.assertIn("Warning: RTT capture is connected but no bytes were recorded yet.", observe_output)
        self.assertIn("If RTT should be active, check your capture configuration.", observe_output)

    def test_prompt_can_read_intent_from_stdin(self) -> None:
        stdin = io.StringIO("The system should remain in READY state.")
        with patch.object(sys, "stdin", stdin):
            output = self._run_cli(
                [
                    "prompt",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--goal",
                    "Compare current state with the intended one",
                    "--intent-file",
                    "-",
                ]
            )
        self.assertIn("The system should remain in READY state.", output)

    def test_snapshot_can_read_gdb_mi_from_stdin_stream(self) -> None:
        stdin = io.StringIO((FIXTURES / "sample.mi").read_text(encoding="utf-8"))
        with patch.object(sys, "stdin", stdin):
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi-stream",
                    "--format",
                    "json",
                ]
            )
        payload = json.loads(output)
        self.assertEqual(payload["stop_reason"], "breakpoint-hit")

    def test_snapshot_can_read_gdb_mi_dash(self) -> None:
        stdin = io.StringIO((FIXTURES / "sample.mi").read_text(encoding="utf-8"))
        with patch.object(sys, "stdin", stdin):
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    "-",
                    "--format",
                    "json",
                ]
            )
        payload = json.loads(output)
        self.assertEqual(payload["frames"][0]["func"], "main")

    def test_snapshot_exports_raw_inputs_on_parse_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_path = workspace / "bad.mi"
            bad_line = '^done,locals=[{name="x",value="'
            mi_path.write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8") + f"\n{bad_line}\n",
                encoding="utf-8",
            )
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(mi_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)
            provenance = payload["provenance"]
            self.assertTrue(provenance.get("raw_exported"))
            self.assertTrue(Path(provenance["gdb_mi_raw_path"]).exists())

    def test_snapshot_exports_rtt_sidecar_on_parse_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_path = workspace / "bad.mi"
            mi_path.write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8") + "\n# non-mi line\n",
                encoding="utf-8",
            )
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(mi_path),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)
            provenance = payload["provenance"]
            self.assertTrue(provenance.get("raw_exported"))
            self.assertTrue(Path(provenance["rtt_raw_path"]).exists())

    def test_snapshot_exports_raw_inputs_with_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--workspace-root",
                    str(workspace),
                    "--export-raw",
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)
            provenance = payload["provenance"]
            self.assertTrue(provenance.get("raw_exported"))
            self.assertTrue(Path(provenance["gdb_mi_raw_path"]).exists())

    def test_snapshot_skips_raw_export_when_no_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)
            provenance = payload["provenance"]
            self.assertFalse(provenance.get("raw_exported"))

    def test_snapshot_exports_raw_inputs_on_non_mi_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_path = workspace / "non_mi.mi"
            mi_path.write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8") + "\n# non-mi line\n",
                encoding="utf-8",
            )
            output = self._run_cli(
                [
                    "snapshot",
                    "--gdb-mi",
                    str(mi_path),
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(output)
            provenance = payload["provenance"]
            self.assertTrue(provenance.get("raw_exported"))
            self.assertTrue(Path(provenance["gdb_mi_raw_path"]).exists())

    def test_observe_exports_raw_inputs_to_state_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_path = workspace / "bad.mi"
            mi_path.write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8") + "\n# non-mi line\n",
                encoding="utf-8",
            )
            snapshot_path = workspace / "snapshots" / "snapshot.json"
            output = self._run_cli(
                [
                    "observe",
                    "--gdb-mi",
                    str(mi_path),
                    "--workspace-root",
                    str(workspace),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            self.assertIn("Saved snapshot", output)
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            provenance = payload["provenance"]
            self.assertTrue(provenance.get("raw_exported"))
            self.assertTrue(Path(provenance["gdb_mi_raw_path"]).exists())

    def test_thin_snapshot_surfaces_missing_evidence_gaps(self) -> None:
        stopped_line = (FIXTURES / "sample.mi").read_text(encoding="utf-8").splitlines()[0]
        with tempfile.NamedTemporaryFile("w", suffix=".mi", delete=False) as handle:
            handle.write(f"{stopped_line}\n")
            path = handle.name
        try:
            output = self._run_cli(["report", "--gdb-mi", path])
        finally:
            Path(path).unlink()
        self.assertIn("No register-values record was found", output)
        self.assertIn("No watched values or locals were captured", output)
        self.assertIn("No RTT lines were available for this snapshot.", output)

    def test_report_fails_with_corrupt_snapshot_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("{ not json")
            path = handle.name
        try:
            code, stdout, stderr = self._run_cli_expect_system_exit(["report", "--snapshot-file", path])
        finally:
            Path(path).unlink()
        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("Could not parse snapshot JSON", message)
        self.assertIn("report failed to load snapshot", message)

    def test_prompt_fails_with_corrupt_snapshot_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("{ not json")
            path = handle.name
        try:
            code, stdout, stderr = self._run_cli_expect_system_exit(
                [
                    "prompt",
                    "--snapshot-file",
                    path,
                    "--goal",
                    "Summarize what this trace indicates.",
                ]
            )
        finally:
            Path(path).unlink()
        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("Could not parse snapshot JSON", message)
        self.assertIn("prompt failed to load snapshot", message)

    def test_snapshot_fails_with_corrupt_snapshot_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("{ not json")
            path = handle.name
        try:
            code, stdout, stderr = self._run_cli_expect_system_exit(
                ["snapshot", "--snapshot-file", path, "--format", "json"]
            )
        finally:
            Path(path).unlink()
        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("Could not parse snapshot JSON", message)
        self.assertIn("snapshot failed to load snapshot", message)

    def test_cli_version_reports_expected_value(self) -> None:
        code, stdout, stderr = self._run_cli_expect_system_exit(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.strip(), "0.1.0")
        self.assertEqual(stderr, "")

    def _run_cli(
        self,
        argv: list[str],
        *,
        capture_stderr: bool = False,
    ) -> str | tuple[str, str]:
        buffer = io.StringIO()
        if capture_stderr:
            stderr = io.StringIO()
            with redirect_stdout(buffer), redirect_stderr(stderr):
                exit_code = main(argv)
            self.assertEqual(exit_code, 0)
            return buffer.getvalue(), stderr.getvalue()
        with redirect_stdout(buffer):
            exit_code = main(argv)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def _run_cli_expect_system_exit(
        self,
        argv: list[str],
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as error:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main(argv)
        exit_payload = error.exception.code
        stderr_text = stderr.getvalue()
        if not isinstance(exit_payload, int) and exit_payload is not None:
            exit_text = str(exit_payload)
            if exit_text:
                stderr_text = (
                    f"{stderr_text.rstrip()}\n{exit_text}\n"
                    if stderr_text
                    else f"{exit_text}\n"
                )
        return (
            exit_payload if isinstance(exit_payload, int) else 1,
            stdout.getvalue(),
            stderr_text,
        )


if __name__ == "__main__":
    unittest.main()
