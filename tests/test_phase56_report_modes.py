from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


class Phase56ReportModesTests(unittest.TestCase):
    def test_default_report_surfaces_unsafe_trust_header_for_running_target_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(
                Path(tmpdir) / "latest_snapshot.json",
                live_state={"backend": "demo", "target_state": "running", "warnings": []},
            )
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        self.assertIn("Trust:", output)
        self.assertIn("UNSAFE", output)
        self.assertIn("not safe for grounded reasoning", output)
        self.assertIn("Target state 'running' is not safe for correlated live reads.", output)
        self.assertNotIn("Session Summary:", output)

    def test_report_allow_unsafe_restores_full_report_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(
                Path(tmpdir) / "latest_snapshot.json",
                live_state={"backend": "demo", "target_state": "running", "warnings": []},
            )
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--allow-unsafe"]
            )

        self.assertIn("Trust:", output)
        self.assertIn("UNSAFE", output)
        self.assertIn("Session Summary:", output)

    def test_explicit_snapshot_ignores_unrelated_newer_workspace_raw_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_dir = root / "snapshot"
            workspace_dir = root / "workspace"
            snapshot_dir.mkdir()
            workspace_dir.mkdir()
            snapshot_path = self._write_snapshot(snapshot_dir / "latest_snapshot.json")
            (workspace_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            snapshot_time = 1_700_000_000
            raw_time = snapshot_time + 300
            os.utime(snapshot_path, (snapshot_time, snapshot_time))
            os.utime(workspace_dir / "cortex-debug-shared-mi.log", (raw_time, raw_time))
            os.utime(workspace_dir / "session.rtt", (raw_time, raw_time))

            output = self._run_cli(
                [
                    "report",
                    "--workspace-root",
                    str(workspace_dir),
                    "--snapshot-file",
                    str(snapshot_path),
                    "--gdb",
                ]
            )

        payload = json.loads(output)
        self.assertEqual(payload["trust"]["verdict"], "safe")
        self.assertNotIn("Raw evidence is newer than the snapshot.", payload["trust"]["reasons"])

    def test_report_vars_outputs_grouped_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--vars"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "variables"})
        self.assertEqual(
            list(payload["variables"].keys()),
            ["locals", "globals", "watchpoints", "unknown"],
        )
        self.assertEqual(payload["variables"]["locals"][0]["name"], "system_state")

    def test_report_vars_filters_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--vars", "SYSTEM_STATE"])

        payload = json.loads(output)
        self.assertEqual([entry["name"] for entry in payload["variables"]["locals"]], ["system_state"])
        self.assertEqual(payload["variables"]["globals"], [])

    def test_report_gdb_outputs_embedded_event_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--gdb"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "gdb"})
        self.assertIn("events", payload["gdb"])
        self.assertGreater(payload["gdb"]["total_event_count"], 0)
        self.assertTrue(payload["metadata"]["snapshot_id"].startswith("snap-"))
        self.assertEqual(payload["metadata"]["source_availability"]["gdb"], "present")

    def test_report_rtt_outputs_embedded_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--rtt"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "rtt"})
        self.assertEqual(payload["rtt"]["lines"][0], "[00:00.001] boot start")
        self.assertEqual(payload["metadata"]["source_availability"]["rtt"], "present")

    def test_report_verbose_outputs_composite_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--verbose"])

        payload = json.loads(output)
        self.assertIn("trust", payload)
        self.assertIn("summary", payload)
        self.assertIn("variables", payload)
        self.assertIn("gdb", payload)
        self.assertIn("rtt", payload)
        self.assertIn("provenance", payload)

    def test_report_combines_requested_inspect_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--vars", "--gdb"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "variables", "gdb"})

    def test_report_tail_applies_to_stream_sections_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--gdb", "--tail", "2"])

        payload = json.loads(output)
        self.assertEqual(payload["gdb"]["event_count"], 2)

    def test_report_tail_requires_stream_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(["report", "--snapshot-file", str(snapshot_path), "--vars", "--tail", "1"])

        self.assertNotEqual(code, 0)
        self.assertIn("--tail requires", stdout + stderr)

    def test_default_report_is_plain_text_with_decision_block_and_source_aware_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        self.assertIn("DebugOracle Evidence Report", output)
        self.assertIn("Trust:", output)
        self.assertIn("Current State:", output)
        self.assertIn("Gaps:", output)
        self.assertIn("Next Useful Commands:", output)
        self.assertIn("`report --gdb --tail 50`", output)
        self.assertIn("`report --rtt --tail 50`", output)
        self.assertIn("`fetch --svd-file <file>`", output)
        self.assertIn("GDB embedded source data: present", output)
        self.assertIn("RTT embedded source data: present", output)

    def _write_snapshot(self, path: Path, live_state: dict | None = None) -> Path:
        bundle = build_bundle_from_files(
            str(FIXTURES / "sample.mi"),
            str(FIXTURES / "sample.rtt"),
        )
        if live_state is not None:
            bundle.live_state = live_state
        save_bundle(bundle, str(path))
        return path

    def _run_cli(self, argv: list[str]) -> str:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        if exit_code != 0:
            raise AssertionError(stderr.getvalue() or stdout.getvalue())
        return stdout.getvalue()

    def _run_cli_expect_system_exit(self, argv: list[str]) -> tuple[int, str, str]:
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
                stderr_text = (f"{stderr_text.rstrip()}\n{exit_text}\n" if stderr_text else f"{exit_text}\n")
        return (exit_payload if isinstance(exit_payload, int) else 1, stdout.getvalue(), stderr_text)


if __name__ == "__main__":
    unittest.main()
