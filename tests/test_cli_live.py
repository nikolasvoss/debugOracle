from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


class DebugOracleLiveCliTests(unittest.TestCase):
    def test_status_command_reports_session_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir)
            output = self._run_cli(["status", "--workspace-root", tmpdir])

        self.assertIn("DebugOracle Session Status", output)
        self.assertIn("Health: healthy", output)
        self.assertIn("Snapshot ID: snap-", output)
        self.assertIn("RTT Capture:", output)
        self.assertIn("Transport Status: no managed capture detected", output)

    def test_status_defaults_to_current_workspace_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir)
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                output = self._run_cli(["status"])
            finally:
                os.chdir(previous)

        self.assertIn("Health: healthy", output)
        self.assertIn("Transport Status: ", output)

    def test_status_command_keeps_missing_rtt_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir, include_rtt=False)
            output = self._run_cli(["status", "--workspace-root", tmpdir])

        self.assertIn("Health: healthy", output)
        self.assertIn("RTT file not found", output)
        self.assertIn("Snapshot Parse Warnings: 1", output)

    def test_status_command_reports_connected_but_empty_managed_rtt_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir, include_rtt=True, include_rtt_state=True, rtt_bytes=0)
            output = self._run_cli(["status", "--workspace-root", tmpdir])

        self.assertIn("Transport Status: connected", output)
        self.assertIn("Bytes Captured: 0", output)
        self.assertIn("RTT capture connected but no bytes were captured yet.", output)

    def test_live_status_command_uses_demo_backend(self) -> None:
        output = self._run_cli(["live-status"])
        self.assertIn("DebugOracle Live Backend Status", output)
        self.assertIn("Backend: demo", output)
        self.assertIn("Available: yes", output)

    def test_live_registers_command_renders_registers(self) -> None:
        output = self._run_cli(["live-registers"])
        self.assertIn("DebugOracle Live Registers", output)
        self.assertIn("pc: 0x08000100", output)
        self.assertIn("sp: 0x20002000", output)

    def test_live_memory_command_renders_memory_payload(self) -> None:
        output = self._run_cli(
            ["live-memory", "--address", "0x20002000", "--size", "8"]
        )
        self.assertIn("DebugOracle Live Memory", output)
        self.assertIn("Address: 0x20002000", output)
        self.assertIn("DebugOra", output)

    def test_live_status_command_rejects_unknown_backend(self) -> None:
        with self.assertRaises(SystemExit) as error:
            main(["live-status", "--backend", "missing"])
        self.assertIn("Unknown live backend", str(error.exception))

    def _run_cli(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(argv)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def _prepare_workspace(
        self,
        tmpdir: str,
        *,
        include_rtt: bool = True,
        include_rtt_state: bool = False,
        rtt_bytes: int | None = None,
    ) -> None:
        workspace = Path(tmpdir)
        session_dir = workspace / ".dbgoracle"
        session_dir.mkdir()
        bundle = build_bundle_from_files(
            str(FIXTURES / "sample.mi"),
            str(FIXTURES / "sample.rtt") if include_rtt else None,
        )
        save_bundle(bundle, str(session_dir / "latest_snapshot.json"))
        (session_dir / "cortex-debug-shared-mi.log").write_text(
            (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        if include_rtt:
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        if include_rtt_state:
            bytes_captured = 0 if rtt_bytes is None else rtt_bytes
            (session_dir / "session.rtt.state.json").write_text(
                (
                    "{\n"
                    '  "source": "openocd-rtt-tcp",\n'
                    '  "host": "127.0.0.1",\n'
                    '  "port": 60001,\n'
                    '  "status": "connected",\n'
                    '  "connected_at": "2026-03-16T10:00:00+00:00",\n'
                    '  "last_byte_at": null,\n'
                    f'  "bytes_captured": {bytes_captured},\n'
                    '  "error": null\n'
                    "}\n"
                ),
                encoding="utf-8",
            )
            if include_rtt and rtt_bytes == 0:
                (session_dir / "session.rtt").write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
