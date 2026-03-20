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
from debugoracle.cli.main import build_parser


FIXTURES = Path(__file__).parent / "fixtures"


class DebugOracleCliTests(unittest.TestCase):
    def test_fetch_exists_and_observe_snapshot_commands_are_gone(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["fetch"])

        self.assertEqual(parsed.command, "fetch")

        with self.assertRaises(SystemExit):
            parser.parse_args(["observe"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["snapshot"])

    def test_report_rejects_removed_legacy_flags(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["report", "--format", "json"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["report", "--var-scope", "all"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["report", "--var-name", "system_state"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["report", "--var-detail", "full"])

    def test_fetch_writes_latest_snapshot_and_prints_operational_summary(self) -> None:
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
                stdout, stderr = self._run_cli(["fetch"], capture_stderr=True)
            finally:
                os.chdir(previous)

            snapshot_path = workspace / "latest_snapshot.json"
            self.assertTrue(snapshot_path.exists())
            self.assertIn("Snapshot ID:", stdout)
            self.assertIn("Output Path:", stdout)
            self.assertIn(str(snapshot_path), stdout)
            self.assertIn("Embedded Sources:", stdout)
            self.assertIn("Source Sizes/Counts:", stdout)
            self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_report_notes_when_svd_register_data_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        lowered = output.lower()
        self.assertIn("peripheral register data is not available in this snapshot", lowered)
        self.assertIn("fetch --svd-file", output)

    def test_report_requires_snapshot_and_tells_user_to_run_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                code, stdout, stderr = self._run_cli_expect_system_exit(["report"])
            finally:
                os.chdir(previous)

        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("report requires a snapshot", message)
        self.assertIn("run `fetch`", message)

    def test_prompt_requires_snapshot_and_tells_user_to_run_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                code, stdout, stderr = self._run_cli_expect_system_exit(
                    ["prompt", "--goal", "Explain why the target stopped here"]
                )
            finally:
                os.chdir(previous)

        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("prompt requires a snapshot", message)
        self.assertIn("run `fetch`", message)

    def test_report_vars_outputs_grouped_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--vars"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"variables"})
        self.assertEqual(
            list(payload["variables"].keys()),
            ["locals", "globals", "watchpoints", "unknown"],
        )
        self.assertEqual(payload["variables"]["locals"][0]["name"], "system_state")

    def test_report_gdb_outputs_gdb_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--gdb"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"gdb"})
        self.assertIn("events", payload["gdb"])

    def test_report_rtt_outputs_rtt_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--rtt"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"rtt"})
        self.assertIn("lines", payload["rtt"])

    def test_report_verbose_outputs_composite_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--verbose"])

        payload = json.loads(output)
        self.assertIn("summary", payload)
        self.assertIn("variables", payload)
        self.assertIn("gdb", payload)
        self.assertIn("rtt", payload)
        self.assertIn("provenance", payload)

    def test_fetch_with_svd_embeds_register_catalog_and_prints_register_counts(self) -> None:
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
                stdout, stderr = self._run_cli(["fetch", "--svd-file", str(FIXTURES / "sample.svd")], capture_stderr=True)
            finally:
                os.chdir(previous)

            payload = json.loads((workspace / "latest_snapshot.json").read_text(encoding="utf-8"))

        self.assertIn("- regs:", stdout)
        self.assertEqual(payload["sources"]["registers"]["device_name"], "STM32L432KCTest")
        self.assertEqual(payload["sources"]["registers"]["register_count"], 4)
        self.assertEqual(payload["sources"]["registers"]["skipped_count"], 4)

    def test_report_regs_list_outputs_captured_peripherals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--regs-list"])

        payload = json.loads(output)
        self.assertEqual(payload["registers_list"]["device_name"], "STM32L432KCTest")
        self.assertEqual([item["name"] for item in payload["registers_list"]["peripherals"]], ["GPIOA", "RCC"])

    def test_report_regs_list_peripheral_outputs_registers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--regs-list", "GPIOA"])

        payload = json.loads(output)
        self.assertEqual(payload["registers_list"]["peripheral"], "GPIOA")
        self.assertEqual([item["name"] for item in payload["registers_list"]["registers"]], ["MODER", "IDR"])

    def test_report_regs_outputs_filtered_register_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--regs", "GPIOA:MODER", "RCC"])

        payload = json.loads(output)
        self.assertEqual([item["name"] for item in payload["registers"]["peripherals"]], ["GPIOA", "RCC"])
        self.assertEqual(payload["registers"]["peripherals"][0]["registers"][0]["name"], "MODER")
        self.assertEqual(payload["registers"]["peripherals"][0]["registers"][0]["read_status"], "skipped")

    def test_report_regs_list_fails_when_register_data_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(["report", "--snapshot-file", str(snapshot_path), "--regs-list"])

        self.assertNotEqual(code, 0)
        self.assertIn("embedded register source", stdout + stderr)

    def test_report_rejects_invalid_register_selector(self) -> None:
        code, stdout, stderr = self._run_cli_expect_system_exit(["report", "--regs", "GPIOA:"])
        self.assertNotEqual(code, 0)
        self.assertIn("invalid register selector", stdout + stderr)

    def test_report_tail_requires_positive_integer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(
                ["report", "--snapshot-file", str(snapshot_path), "--gdb", "--tail", "0"]
            )

        self.assertNotEqual(code, 0)
        self.assertIn("tail", (stdout + stderr).lower())
        self.assertIn("positive", (stdout + stderr).lower())

    def test_report_vars_fails_when_requested_names_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(
                ["report", "--snapshot-file", str(snapshot_path), "--vars", "definitely_missing"]
            )

        self.assertNotEqual(code, 0)
        self.assertIn("definitely_missing", stdout + stderr)
        self.assertIn("no matches", (stdout + stderr).lower())

    def test_fetch_discovery_failure_lists_checked_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                code, stdout, stderr = self._run_cli_expect_system_exit(["fetch"])
            finally:
                os.chdir(previous)

        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("could not auto-resolve an input source", message)
        self.assertIn("cortex-debug-shared-mi.log", message)
        self.assertIn("session.rtt", message)

    def _write_snapshot(self, path: Path, svd_file: Path | None = None) -> Path:
        bundle = build_bundle_from_files(
            str(FIXTURES / "sample.mi"),
            str(FIXTURES / "sample.rtt"),
            svd_file_path=str(svd_file) if svd_file else None,
        )
        save_bundle(bundle, str(path))
        return path

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
