from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from debugoracle.cli.commands import run_stop
from debugoracle.cli.main import main as package_main
from debugoracle.rtt import RttCaptureState, RttCaptureTimeoutError

main = package_main


def _identity(
    pid: int,
    workspace: Path,
    *,
    start_time_ticks: int = 100,
) -> run_stop.ProcessIdentity:
    return run_stop.ProcessIdentity(
        pid=pid,
        start_time_ticks=start_time_ticks,
        executable=str(Path(sys.executable).resolve()),
        argv=(
            sys.executable,
            "-m",
            "debugoracle",
            "run",
            "--workspace-root",
            str(workspace.resolve()),
        ),
    )


def _write_runtime(
    path: Path, workspace: Path, identity: run_stop.ProcessIdentity
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": run_stop.RUN_METADATA_SCHEMA_VERSION,
                "pid": identity.pid,
                "start_time_ticks": identity.start_time_ticks,
                "executable": identity.executable,
                "argv": list(identity.argv),
                "workspace_root": str(workspace.resolve()),
            }
        ),
        encoding="utf-8",
    )


class DebugOracleRunStopTests(unittest.TestCase):
    def test_process_identity_is_read_from_proc_without_fallback_inference(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proc_root = Path(tmpdir)
            process_dir = proc_root / "42"
            process_dir.mkdir()
            fields_3_through_22 = ["S"] + ["0"] * 18 + ["987654"]
            (process_dir / "stat").write_text(
                "42 (python worker) " + " ".join(fields_3_through_22),
                encoding="utf-8",
            )
            executable = proc_root / "python"
            executable.write_text("", encoding="utf-8")
            (process_dir / "exe").symlink_to(executable)
            argv = ["python", "-m", "debugoracle", "run"]
            (process_dir / "cmdline").write_bytes(
                b"\x00".join(item.encode() for item in argv) + b"\x00"
            )

            identity = run_stop.capture_process_identity(42, proc_root=proc_root)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.start_time_ticks, 987654)
        self.assertEqual(identity.executable, str(executable.resolve()))
        self.assertEqual(identity.argv, tuple(argv))

    def test_stop_refuses_reused_pid_with_different_start_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir).resolve()
            runtime = workspace / ".dbgoracle" / "session.rtt.run.json"
            runtime.parent.mkdir()
            argv = (
                sys.executable,
                "-m",
                "debugoracle",
                "run",
                "--workspace-root",
                str(workspace),
            )
            runtime.write_text(
                json.dumps(
                    {
                        "schema_version": run_stop.RUN_METADATA_SCHEMA_VERSION,
                        "pid": 4242,
                        "start_time_ticks": 100,
                        "executable": str(Path(sys.executable).resolve()),
                        "argv": list(argv),
                        "workspace_root": str(workspace),
                    }
                ),
                encoding="utf-8",
            )
            current = run_stop.ProcessIdentity(
                pid=4242,
                start_time_ticks=101,
                executable=str(Path(sys.executable).resolve()),
                argv=argv,
            )
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    return_value=current,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle"
                ) as handle_signal,
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stderr(stderr),
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])

        self.assertEqual(exit_code, 1)
        handle_signal.assert_not_called()
        self.assertIn("identity mismatch", stderr.getvalue())

    def test_stop_rechecks_identity_before_force_kill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            runtime = workspace / ".dbgoracle" / "session.rtt.run.json"
            runtime.parent.mkdir()
            identity = _identity(4242, workspace)
            changed = run_stop.ProcessIdentity(
                pid=identity.pid,
                start_time_ticks=identity.start_time_ticks + 1,
                executable=identity.executable,
                argv=identity.argv,
            )
            _write_runtime(runtime, workspace, identity)
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=[identity, changed],
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle"
                ) as handle_signal,
                patch(
                    "debugoracle.cli.commands.run_stop.wait_for_process_exit",
                    return_value=False,
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    [
                        "stop",
                        "--workspace-root",
                        str(workspace),
                        "--grace-timeout",
                        "0",
                    ]
                )

        self.assertEqual(exit_code, 1)
        handle_signal.assert_called_once_with(71, run_stop.signal.SIGTERM)
        self.assertIn("SIGKILL was not sent", stderr.getvalue())

    def test_stop_signals_only_through_a_pidfd_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            runtime = workspace / ".dbgoracle" / "session.rtt.run.json"
            runtime.parent.mkdir()
            identity = _identity(4242, workspace)
            _write_runtime(runtime, workspace, identity)
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=[identity, identity, None],
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                    create=True,
                ) as open_handle,
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle",
                    create=True,
                ) as handle_signal,
                patch(
                    "debugoracle.cli.commands.run_stop.wait_for_process_exit",
                    return_value=True,
                    create=True,
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                patch("debugoracle.cli.commands.run_stop.os.kill") as numeric_kill,
            ):
                exit_code = main(
                    [
                        "stop",
                        "--workspace-root",
                        str(workspace),
                        "--grace-timeout",
                        "0",
                    ]
                )

        self.assertEqual(exit_code, 0)
        open_handle.assert_called_once_with(identity.pid)
        handle_signal.assert_called()
        numeric_kill.assert_not_called()

    def test_stop_cleans_stale_metadata_when_pidfd_proves_process_exited(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            runtime = workspace / ".dbgoracle" / "session.rtt.run.json"
            runtime.parent.mkdir()
            identity = _identity(4242, workspace)
            _write_runtime(runtime, workspace, identity)
            stdout = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    side_effect=ProcessLookupError("process exited"),
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle"
                ) as handle_signal,
                redirect_stdout(stdout),
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])

            runtime_exists = runtime.exists()

        self.assertEqual(exit_code, 0)
        handle_signal.assert_not_called()
        self.assertFalse(runtime_exists)
        self.assertIn("stale", stdout.getvalue().lower())

    def test_stop_rejects_symlink_runtime_metadata_without_signaling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = root / "workspace"
            runtime = workspace / ".dbgoracle" / "session.rtt.run.json"
            runtime.parent.mkdir(parents=True)
            identity = _identity(4242, workspace)
            outside = root / "outside.json"
            _write_runtime(outside, workspace, identity)
            before = outside.read_bytes()
            runtime.symlink_to(outside)
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=[identity, None],
                ),
                patch("debugoracle.cli.commands.run_stop.os.kill") as kill,
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])

            self.assertIn(exit_code, {0, 1})
            kill.assert_not_called()
            self.assertEqual(outside.read_bytes(), before)

    def test_stop_terminates_the_exact_recorded_real_process(self) -> None:
        if not Path("/proc/self/stat").exists():
            self.skipTest("Linux /proc is required")
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir).resolve()
            command = [
                sys.executable,
                "-m",
                "debugoracle",
                "run",
                "--workspace-root",
                str(workspace),
                "--host",
                "127.0.0.1",
                "--port",
                "65534",
                "--connect-timeout",
                "30",
                "--poll-interval",
                "0.05",
            ]
            child = subprocess.Popen(  # nosec B603
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                identity = None
                deadline = time.monotonic() + 3.0
                while identity is None and time.monotonic() < deadline:
                    identity = run_stop.capture_process_identity(child.pid)
                    if identity is None:
                        time.sleep(0.02)
                self.assertIsNotNone(identity)
                assert identity is not None
                runtime = workspace / ".dbgoracle" / run_stop.DEFAULT_RUN_METADATA
                runtime.parent.mkdir(parents=True, exist_ok=True)
                _write_runtime(runtime, workspace, identity)
                reaper = threading.Thread(target=child.wait, daemon=True)
                reaper.start()

                exit_code = main(
                    [
                        "stop",
                        "--workspace-root",
                        str(workspace),
                        "--grace-timeout",
                        "2",
                    ]
                )
                reaper.join(timeout=3.0)

                self.assertEqual(exit_code, 0)
                self.assertIsNotNone(child.returncode)
                self.assertFalse(runtime.exists())
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=3.0)

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
                patch(
                    "debugoracle.cli.commands.run_stop.capture_rtt", return_value=state
                ),
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
        self.assertIn(
            "RTT run stopped because the RTT server closed the connection.",
            buffer.getvalue(),
        )

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
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_rtt", return_value=state
                ),
                redirect_stdout(buffer),
            ):
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
        self.assertIn(
            "RTT run stopped because the RTT server closed the connection.",
            buffer.getvalue(),
        )

    def test_run_detach_writes_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            buffer = io.StringIO()
            popen = Mock()
            popen.pid = 23456
            popen.poll.return_value = None
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.subprocess.Popen",
                    return_value=popen,
                ) as popen_mock,
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=lambda pid: run_stop.ProcessIdentity(
                        pid=pid,
                        start_time_ticks=1234,
                        executable="/usr/bin/python",
                        argv=tuple(popen_mock.call_args.args[0]),
                    ),
                ),
                redirect_stdout(buffer),
            ):
                exit_code = main(
                    ["run", "--detach", "--workspace-root", str(workspace)]
                )
            runtime_path = workspace / ".dbgoracle" / "session.rtt.run.json"
            payload = json.loads(runtime_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["pid"], 23456)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["start_time_ticks"], 1234)
        self.assertEqual(payload["argv"], popen_mock.call_args.args[0])
        self.assertEqual(payload["mode"], "detached")
        self.assertIn(
            str(Path(__file__).resolve().parents[1]),
            popen_mock.call_args.kwargs["env"]["PYTHONPATH"],
        )
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
                patch(
                    "debugoracle.cli.commands.run_stop.subprocess.Popen",
                    return_value=popen,
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["run", "--detach", "--workspace-root", str(workspace)]
                )
            runtime_path = workspace / ".dbgoracle" / "session.rtt.run.json"
        self.assertEqual(exit_code, 1)
        self.assertFalse(runtime_path.exists())
        self.assertIn("exited during startup", stderr.getvalue())

    def test_run_detach_force_kills_child_when_proc_identity_is_unavailable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stderr = io.StringIO()
            popen = Mock()
            popen.pid = 23456
            popen.poll.return_value = None
            popen.wait.side_effect = [
                subprocess.TimeoutExpired(cmd="dbgoracle run", timeout=1.0),
                0,
            ]
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.subprocess.Popen",
                    return_value=popen,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    return_value=None,
                ),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["run", "--detach", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 1)
        popen.terminate.assert_called_once_with()
        popen.kill.assert_called_once_with()
        self.assertIn("child was stopped", stderr.getvalue())

    def test_run_detach_stops_child_when_runtime_metadata_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stderr = io.StringIO()
            popen = Mock()
            popen.pid = 23456
            popen.poll.return_value = None
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.subprocess.Popen",
                    return_value=popen,
                ) as popen_mock,
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=lambda pid: run_stop.ProcessIdentity(
                        pid=pid,
                        start_time_ticks=1234,
                        executable="/usr/bin/python",
                        argv=tuple(popen_mock.call_args.args[0]),
                    ),
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.atomic_write_text",
                    side_effect=run_stop.SafeIOError("disk full"),
                ),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["run", "--detach", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 1)
        popen.terminate.assert_called_once_with()
        popen.wait.assert_called()
        self.assertIn("runtime metadata", stderr.getvalue().lower())

    def test_run_foreground_returns_timeout_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            with patch(
                "debugoracle.cli.commands.run_stop.capture_rtt",
                side_effect=RttCaptureTimeoutError("timeout"),
            ):
                exit_code = main(["run", "--port", "60001", "--output", str(output)])
        self.assertEqual(exit_code, 2)

    def test_run_detach_reports_already_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            runtime = session_dir / "session.rtt.run.json"
            identity = _identity(7777, workspace)
            _write_runtime(runtime, workspace, identity)
            buffer = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    return_value=identity,
                ),
                patch("debugoracle.cli.commands.run_stop.subprocess.Popen") as popen,
                redirect_stdout(buffer),
            ):
                exit_code = main(
                    ["run", "--detach", "--workspace-root", str(workspace)]
                )
        self.assertEqual(exit_code, 0)
        popen.assert_not_called()
        self.assertIn("Detached RTT run already active", buffer.getvalue())

    def test_stop_stops_owned_pid_and_cleans_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            runtime = session_dir / "session.rtt.run.json"
            identity = _identity(4242, workspace)
            _write_runtime(runtime, workspace, identity)
            buffer = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    return_value=identity,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle"
                ) as handle_signal,
                patch(
                    "debugoracle.cli.commands.run_stop.wait_for_process_exit",
                    return_value=True,
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stdout(buffer),
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])
        self.assertEqual(exit_code, 0)
        handle_signal.assert_called_once_with(71, run_stop.signal.SIGTERM)
        self.assertFalse(runtime.exists())
        self.assertIn("Stopped detached RTT run", buffer.getvalue())

    def test_stop_refuses_unowned_pid_and_preserves_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            runtime = session_dir / "session.rtt.run.json"
            identity = _identity(3131, workspace)
            _write_runtime(runtime, workspace, identity)
            unrelated = run_stop.ProcessIdentity(
                pid=3131,
                start_time_ticks=identity.start_time_ticks,
                executable=identity.executable,
                argv=("python", "unrelated.py"),
            )
            buffer = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    return_value=unrelated,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle"
                ) as handle_signal,
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stderr(buffer),
            ):
                exit_code = main(["stop", "--workspace-root", str(workspace)])
            runtime_preserved = runtime.exists()
        self.assertEqual(exit_code, 1)
        handle_signal.assert_not_called()
        self.assertTrue(runtime_preserved)
        self.assertIn("identity mismatch", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
