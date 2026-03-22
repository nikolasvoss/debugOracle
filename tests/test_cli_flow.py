from __future__ import annotations

import io
import json
import os
import socketserver
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.cli import main
from debugoracle.cli.main import build_parser


FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_OPENOCD_VALUES = {
    0x48000000: "0xaaaaaaaa",
    0x48000010: "0x00000001",
}


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

    def test_fetch_writes_latest_snapshot_and_prints_agent_summary(self) -> None:
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
            self.assertIn("DebugOracle Fetch Summary", stdout)
            self.assertIn("Outcome:", stdout)
            self.assertIn("Evidence:", stdout)
            self.assertIn("Next:", stdout)
            self.assertIn("Snapshot saved:", stdout)
            self.assertIn(str(snapshot_path), stdout)
            self.assertIn("GDB: present", stdout)
            self.assertIn("RTT: present", stdout)
            self.assertIn("Registers: absent", stdout)
            self.assertIn(f"dbgoracle report --workspace-root {workspace.resolve()}", stdout)
            self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_fetch_next_commands_use_resolved_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as otherdir:
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
                os.chdir(otherdir)
                stdout, _ = self._run_cli(["fetch", "--workspace-root", tmpdir], capture_stderr=True)
            finally:
                os.chdir(previous)

        self.assertIn(f"dbgoracle report --workspace-root {workspace.resolve()}", stdout)
        self.assertNotIn("dbgoracle report --workspace-root .", stdout)

    def test_report_notes_when_svd_register_data_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path)])

        self.assertIn("Gaps:", output)
        self.assertIn("Register data: absent", output)
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
        self.assertEqual(set(payload.keys()), {"trust", "variables"})
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
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "gdb"})
        self.assertIn("events", payload["gdb"])
        self.assertTrue(payload["metadata"]["snapshot_id"].startswith("snap-"))
        self.assertEqual(payload["metadata"]["source_availability"]["gdb"], "present")

    def test_report_rtt_outputs_rtt_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--rtt"])

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "rtt"})
        self.assertIn("lines", payload["rtt"])
        self.assertEqual(payload["metadata"]["source_availability"]["rtt"], "present")

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

    def test_fetch_with_svd_captures_register_values_and_prints_register_guidance(self) -> None:
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

            with _FakeOpenOcdServer(values=DEFAULT_OPENOCD_VALUES) as server:
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", str(FIXTURES / "sample.svd")],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                    capture_stderr=True,
                )

            payload = json.loads((workspace / "latest_snapshot.json").read_text(encoding="utf-8"))

        self.assertIn("Registers: present", stdout)
        self.assertIn(f"dbgoracle report --workspace-root {workspace.resolve()} --regs-list", stdout)
        self.assertEqual(payload["sources"]["registers"]["device_name"], "STM32L432KCTest")
        self.assertEqual(payload["sources"]["registers"]["register_count"], 4)
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)
        self.assertEqual(payload["sources"]["registers"]["skipped_count"], 2)
        self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_report_regs_list_outputs_captured_peripherals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--regs-list"])

        payload = json.loads(output)
        self.assertEqual(payload["registers_list"]["device_name"], "STM32L432KCTest")
        self.assertEqual([item["name"] for item in payload["registers_list"]["peripherals"]], ["GPIOA", "RCC"])
        self.assertEqual(payload["registers_list"]["peripherals"][0]["success_count"], 2)
        self.assertEqual(payload["registers_list"]["peripherals"][1]["skipped_count"], 2)

    def test_report_regs_list_peripheral_outputs_registers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--regs-list", "GPIOA"])

        payload = json.loads(output)
        self.assertEqual(payload["registers_list"]["peripheral"], "GPIOA")
        self.assertEqual([item["name"] for item in payload["registers_list"]["registers"]], ["MODER", "IDR"])
        self.assertEqual([item["read_status"] for item in payload["registers_list"]["registers"]], ["success", "success"])

    def test_report_regs_outputs_filtered_register_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd")
            output = self._run_cli(["report", "--snapshot-file", str(snapshot_path), "--regs", "GPIOA:MODER", "RCC"])

        payload = json.loads(output)
        self.assertEqual([item["name"] for item in payload["registers"]["peripherals"]], ["GPIOA", "RCC"])
        self.assertEqual(payload["registers"]["peripherals"][0]["registers"][0]["name"], "MODER")
        self.assertEqual(payload["registers"]["peripherals"][0]["registers"][0]["read_status"], "success")
        self.assertEqual(payload["registers"]["peripherals"][0]["registers"][0]["value_hex"], "0xaaaaaaaa")
        self.assertEqual(payload["registers"]["peripherals"][1]["registers"][0]["read_status"], "skipped")

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
        if svd_file is None:
            bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
                svd_file_path=None,
            )
        else:
            with _FakeOpenOcdServer(values=DEFAULT_OPENOCD_VALUES) as server:
                with patch.dict(
                    os.environ,
                    {
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                    clear=False,
                ):
                    bundle = build_bundle_from_files(
                        str(FIXTURES / "sample.mi"),
                        str(FIXTURES / "sample.rtt"),
                        svd_file_path=str(svd_file),
                        enable_live_peripheral_capture=True,
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

    def _run_cli_in_workspace(
        self,
        workspace: Path,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        capture_stderr: bool = False,
    ) -> str | tuple[str, str]:
        previous = os.getcwd()
        try:
            os.chdir(workspace)
            with patch.dict(os.environ, env or {}, clear=False):
                return self._run_cli(argv, capture_stderr=capture_stderr)
        finally:
            os.chdir(previous)


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
