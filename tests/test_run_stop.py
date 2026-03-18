from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from debugoracle.cli import main
from debugoracle.cli.main import main as package_main
from debugoracle.rtt import RttCaptureState, RttCaptureTimeoutError


class DebugOracleRunStopTests(unittest.TestCase):
    def test_package_main_routes_run_through_run_stop_command_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            state = RttCaptureState(
                source="openocd-rtt-tcp",
                host="127.0.0.1",
                port=60001,
                status="eof",
                connected_at="2026-03-17T00:00:00+00:00",
                last_byte_at="2026-03-17T00:00:01+00:00",
                bytes_captured=12,
                error=None,
            )
            buffer = io.StringIO()
            with (
                patch("debugoracle.cli.commands.run_stop.capture_rtt", return_value=state),
                redirect_stdout(buffer),
            ):
                exit_code = package_main(
                    [
                        "run",
                        "--port",
                        "60001",
                        "--output",
                        str(output),
                    ]
                )
        self.assertEqual(exit_code, 0)
        self.assertIn("RTT run stopped because the RTT server closed the connection.", buffer.getvalue())

    def test_run_foreground_reports_eof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            state = RttCaptureState(
                source="openocd-rtt-tcp",
                host="127.0.0.1",
                port=60001,
                status="eof",
                connected_at="2026-03-17T00:00:00+00:00",
                last_byte_at="2026-03-17T00:00:01+00:00",
                bytes_captured=12,
                error=None,
            )
            buffer = io.StringIO()
            with patch("debugoracle.cli.commands.run_stop.capture_rtt", return_value=state), redirect_stdout(buffer):
                exit_code = main(
                    [
                        "run",
                        "--port",
                        "60001",
                        "--output",
                        str(output),
                    ]
                )
        self.assertEqual(exit_code, 0)
        self.assertIn("RTT run stopped because the RTT server closed the connection.", buffer.getvalue())

    def test_run_detach_writes_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            buffer = io.StringIO()
            popen = Mock()
            popen.pid = 23456
            popen.poll.return_value = None
            with patch("debugoracle.cli.commands.run_stop.subprocess.Popen", return_value=popen), redirect_stdout(buffer):
                exit_code = main(["run", "--detach", "--workspace-root", str(workspace)])
            runtime_path = workspace / ".dbgoracle" / "session.rtt.run.json"
            payload = json.loads(runtime_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["pid"], 23456)
        self.assertEqual(payload["mode"], "detached")
        self.assertIn("Started detached RTT run", buffer.getvalue())

    def test_run_detach_fails_when_child_exits_during_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout = io.StringIO()
            stderr = io.StringIO()
            popen = Mock()
            popen.pid = 12345
            popen.poll.return_value = 1
            with (
                patch("debugoracle.cli.commands.run_stop.subprocess.Popen", return_value=popen),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(["run", "--detach", "--workspace-root", str(workspace)])
            runtime_path = workspace / ".dbgoracle" / "session.rtt.run.json"
        self.assertEqual(exit_code, 1)
        self.assertFalse(runtime_path.exists())
        self.assertIn("exited during startup", stderr.getvalue())

    def test_run_foreground_returns_timeout_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            with patch("debugoracle.cli.commands.run_stop.capture_rtt", side_effect=RttCaptureTimeoutError("timeout")):
                exit_code = main(["run", "--port", "60001", "--output", str(output)])
        self.assertEqual(exit_code, 2)

    def test_run_detach_reports_already_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            runtime = session_dir / "session.rtt.run.json"
            runtime.write_text(json.dumps({"pid": 7777}), encoding="utf-8")
            buffer = io.StringIO()
            with (
                patch("debugoracle.cli.commands.run_stop.is_pid_running", return_value=True),
                patch("debugoracle.cli.commands.run_stop.is_owned_run_process", return_value=True),
                patch("debugoracle.cli.commands.run_stop.subprocess.Popen") as popen,
                redirect_stdout(buffer),
            ):
                exit_code = main(["run", "--detach", "--workspace-root", str(workspace)])
        self.assertEqual(exit_code, 0)
        popen.assert_not_called()
        self.assertIn("Detached RTT run already active", buffer.getvalue())

    def test_stop_stops_owned_pid_and_cleans_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            runtime = session_dir / "session.rtt.run.json"
            runtime.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
            buffer = io.StringIO()
            with (
                patch("debugoracle.cli.commands.run_stop.is_pid_running", side_effect=[True, False]),
                patch("debugoracle.cli.commands.run_stop.is_owned_run_process", return_value=True),
                patch("debugoracle.cli.commands.run_stop.os.kill") as kill,
                redirect_stdout(buffer),
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])
        self.assertEqual(exit_code, 0)
        kill.assert_called()
        self.assertFalse(runtime.exists())
        self.assertIn("Stopped detached RTT run", buffer.getvalue())

    def test_stop_refuses_unowned_pid_and_cleans_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            runtime = session_dir / "session.rtt.run.json"
            runtime.write_text(json.dumps({"pid": 3131}), encoding="utf-8")
            buffer = io.StringIO()
            with (
                patch("debugoracle.cli.commands.run_stop.is_pid_running", return_value=True),
                patch("debugoracle.cli.commands.run_stop.is_owned_run_process", return_value=False),
                patch("debugoracle.cli.commands.run_stop.os.kill") as kill,
                redirect_stdout(buffer),
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])
        self.assertEqual(exit_code, 0)
        kill.assert_not_called()
        self.assertFalse(runtime.exists())
        self.assertIn("Refusing to stop pid 3131", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
