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

from debugoracle.builder import build_bundle_from_text
from debugoracle.sources.debuggers.gdb.peripheral_registers import parse_svd_definition
from debugoracle.cli import main
from debugoracle.cli.main import build_parser


FIXTURES = Path(__file__).parent / "fixtures"


class FetchPhase3Tests(unittest.TestCase):
    def test_fetch_with_svd_captures_safe_peripheral_registers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={
                    0x40000000: "0x00000011",
                    0x40000004: "0x00000022",
                }
            ) as server:
                stdout, _ = self._run_cli_in_workspace(
                    workspace,
                    [
                        "fetch",
                        "--svd-file",
                        "test.svd",
                    ],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                    capture_stderr=True,
                )

            snapshot_path = workspace / "latest_snapshot.json"
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            registers = payload["sources"]["registers"]
            self.assertEqual(registers["success_count"], 2)
            self.assertEqual(registers["failure_count"], 0)
            self.assertEqual(registers["skipped_count"], 1)
            self.assertIn("- regs: 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped", stdout)

    def test_fetch_with_svd_fails_when_recent_mi_tail_ends_in_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                '*stopped,reason="breakpoint-hit"\n*running,thread-id="all"\n',
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(values={0x40000000: "0x00000011"}) as server:
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                )

            self.assertNotEqual(code, 0)
            self.assertIn("requires a recent halted target in the GDB/MI log", stdout + stderr)

    def test_fetch_with_svd_fails_when_recent_mi_tail_has_no_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                "^done,stack=[]\n^done,register-values=[]\n",
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(values={0x40000000: "0x00000011"}) as server:
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                )

            self.assertNotEqual(code, 0)
            self.assertIn("requires a recent halted target in the GDB/MI log", stdout + stderr)

    def test_fetch_with_svd_fails_when_no_register_reads_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(values={}) as server:
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                )

            self.assertNotEqual(code, 0)
            self.assertIn("did not read any register values successfully", stdout + stderr)
    def test_parse_svd_definition_resolves_derived_peripherals_from_real_example(self) -> None:
        definition = parse_svd_definition(str(Path(__file__).resolve().parents[1] / "examples" / "STM32L432.svd"))

        peripherals = {peripheral.name: peripheral for peripheral in definition.peripherals}
        self.assertIn("GPIOC", peripherals)
        self.assertIn("GPIOE", peripherals)
        self.assertIn("DMA1", peripherals)
        self.assertIn("DMA2", peripherals)
        self.assertEqual(peripherals["GPIOE"].base_address, "0x48001000")
        self.assertEqual(peripherals["DMA2"].base_address, "0x40020400")
        self.assertGreater(len(peripherals["GPIOE"].registers), 0)
        self.assertGreater(len(peripherals["DMA2"].registers), 0)
        self.assertIn("MODER", {register.name for register in peripherals["GPIOE"].registers})
        self.assertIn("ISR", {register.name for register in peripherals["DMA2"].registers})

    def test_fetch_command_replaces_observe_and_snapshot(self) -> None:
        parser = build_parser()

        fetch_args = parser.parse_args(["fetch", "--gdb-mi", "sample.mi"])
        self.assertEqual(fetch_args.command, "fetch")

        with self.assertRaises(SystemExit):
            parser.parse_args(["observe"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["snapshot"])

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
            self.assertIn("Embedded Sources: gdb, rtt", stdout)
            self.assertIn("Source Sizes/Counts:", stdout)
            self.assertIn("- gdb:", stdout)
            self.assertIn("- rtt:", stdout)
            self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_fetch_discovery_failure_lists_checked_raw_candidates(self) -> None:
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
        self.assertNotIn("--snapshot-file", message)
        self.assertNotIn("latest_snapshot.json", message)

    def test_snapshot_keeps_full_embedded_rtt_when_recent_window_is_trimmed(self) -> None:
        bundle = build_bundle_from_text("^done\n", "line one\nline two\nline three\n", rtt_window=2)

        self.assertEqual(bundle.recent_rtt, ["line two", "line three"])
        self.assertEqual(bundle.sources.rtt.lines, ["line one", "line two", "line three"])
        self.assertEqual(bundle.sources.rtt.raw_text, "line one\nline two\nline three\n")

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

    def _run_cli_expect_system_exit_in_workspace(
        self,
        workspace: Path,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        previous = os.getcwd()
        try:
            os.chdir(workspace)
            with patch.dict(os.environ, env or {}, clear=False):
                return self._run_cli_expect_system_exit(argv)
        finally:
            os.chdir(previous)


def _minimal_svd_text() -> str:
    return """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<device>
  <name>TESTMCU</name>
  <peripherals>
    <peripheral>
      <name>TEST</name>
      <baseAddress>0x40000000</baseAddress>
      <registers>
        <register>
          <name>CTRL</name>
          <addressOffset>0x0</addressOffset>
          <size>32</size>
          <access>read-write</access>
        </register>
        <register>
          <name>STATUS</name>
          <addressOffset>0x4</addressOffset>
          <size>32</size>
          <access>read-only</access>
        </register>
        <register>
          <name>WRITEONLY</name>
          <addressOffset>0x8</addressOffset>
          <size>32</size>
          <access>write-only</access>
        </register>
      </registers>
    </peripheral>
  </peripherals>
</device>
"""


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
