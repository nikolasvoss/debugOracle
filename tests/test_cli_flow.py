from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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

    def test_corrupt_snapshot_file_still_renders_report(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("{ not json")
            path = handle.name
        try:
            output = self._run_cli(["report", "--snapshot-file", path])
        finally:
            Path(path).unlink()
        self.assertIn("DebugOracle Evidence Report", output)
        self.assertIn("MI/RTT parsing warnings", output)

    def _run_cli(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(argv)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
