from __future__ import annotations

import importlib
import io
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from debugoracle import main as package_entry
from debugoracle.cli import main as cli_main
from debugoracle.cli.commands import run_stop
from debugoracle.rtt import RttCaptureState


cli_main_module = importlib.import_module("debugoracle.cli.main")


def _identity(pid: int, workspace: Path) -> run_stop.ProcessIdentity:
    return run_stop.ProcessIdentity(
        pid=pid,
        start_time_ticks=100,
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


class EntryPointTests(unittest.TestCase):
    def test_package_main_delegates_to_cli_main(self) -> None:
        with patch.object(cli_main_module, "main", return_value=7) as main_mock:
            exit_code = package_entry(["status"])
        self.assertEqual(exit_code, 7)
        main_mock.assert_called_once_with(["status"])

    def test_module_main_raises_system_exit_with_cli_code(self) -> None:
        with patch.object(cli_main_module, "main", return_value=3):
            with self.assertRaises(SystemExit) as cm:
                runpy.run_module("debugoracle", run_name="__main__")
        self.assertEqual(cm.exception.code, 3)


class RunStopHelpersTests(unittest.TestCase):
    def test_stop_handles_missing_runtime_invalid_pid_and_non_running_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["stop", "--workspace-root", str(workspace)])
            self.assertEqual(code, 0)
            self.assertIn("No detached RTT run is active", stdout.getvalue())

            runtime = workspace / ".dbgoracle" / run_stop.DEFAULT_RUN_METADATA
            runtime.parent.mkdir(parents=True, exist_ok=True)
            runtime.write_text(json.dumps({"pid": "abc"}), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["stop", "--workspace-root", str(workspace)])
            self.assertEqual(code, 0)
            self.assertIn("Invalid runtime metadata", stdout.getvalue())
            self.assertFalse(runtime.exists())

            identity = _identity(9999, workspace)
            _write_runtime(runtime, workspace, identity)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["stop", "--workspace-root", str(workspace)])
            self.assertEqual(code, 0)
            self.assertIn("stale", stdout.getvalue().lower())
            self.assertFalse(runtime.exists())

    def test_stop_reports_signal_and_force_kill_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            runtime = workspace / ".dbgoracle" / run_stop.DEFAULT_RUN_METADATA
            runtime.parent.mkdir(parents=True, exist_ok=True)
            identity = _identity(4242, workspace)
            _write_runtime(runtime, workspace, identity)

            stderr = io.StringIO()
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
                    "debugoracle.cli.commands.run_stop.signal_process_handle",
                    side_effect=OSError("sigterm failed"),
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stderr(stderr),
            ):
                code = cli_main(["stop", "--workspace-root", str(workspace)])
            self.assertEqual(code, 1)
            self.assertIn("Failed to signal detached RTT run", stderr.getvalue())

            _write_runtime(runtime, workspace, identity)
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=[identity, identity],
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.signal_process_handle",
                    side_effect=[None, OSError("sigkill failed")],
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.wait_for_process_exit",
                    return_value=False,
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stderr(stderr),
            ):
                code = cli_main(
                    ["stop", "--workspace-root", str(workspace), "--grace-timeout", "0"]
                )
            self.assertEqual(code, 1)
            self.assertIn("Failed to force-stop", stderr.getvalue())

    def test_stop_force_kill_success_and_remaining_pid_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            runtime = workspace / ".dbgoracle" / run_stop.DEFAULT_RUN_METADATA
            runtime.parent.mkdir(parents=True, exist_ok=True)

            identity = _identity(3333, workspace)
            _write_runtime(runtime, workspace, identity)
            stdout = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=[identity, identity],
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch("debugoracle.cli.commands.run_stop.signal_process_handle"),
                patch(
                    "debugoracle.cli.commands.run_stop.wait_for_process_exit",
                    side_effect=[False, True],
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stdout(stdout),
            ):
                code = cli_main(
                    ["stop", "--workspace-root", str(workspace), "--grace-timeout", "0"]
                )
            self.assertEqual(code, 0)
            self.assertIn("after force-kill", stdout.getvalue())

            _write_runtime(runtime, workspace, identity)
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_process_identity",
                    side_effect=[identity, identity],
                ),
                patch(
                    "debugoracle.cli.commands.run_stop.open_process_handle",
                    return_value=71,
                ),
                patch("debugoracle.cli.commands.run_stop.signal_process_handle"),
                patch(
                    "debugoracle.cli.commands.run_stop.wait_for_process_exit",
                    return_value=False,
                ),
                patch("debugoracle.cli.commands.run_stop.os.close"),
                redirect_stderr(stderr),
            ):
                code = cli_main(
                    ["stop", "--workspace-root", str(workspace), "--grace-timeout", "0"]
                )
            self.assertEqual(code, 1)
            self.assertIn("Failed to stop detached RTT run", stderr.getvalue())

    def test_run_foreground_idle_and_interrupted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            idle_state = RttCaptureState(
                source="openocd-rtt-tcp",
                host="127.0.0.1",
                port=60001,
                status="idle",
                connected_at="2026-03-17T00:00:00+00:00",
                last_byte_at="2026-03-17T00:00:01+00:00",
                bytes_captured=1,
                error=None,
            )
            interrupted_state = RttCaptureState(
                source="openocd-rtt-tcp",
                host="127.0.0.1",
                port=60001,
                status="interrupted",
                connected_at="2026-03-17T00:00:00+00:00",
                last_byte_at="2026-03-17T00:00:01+00:00",
                bytes_captured=1,
                error=None,
            )

            stdout = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_rtt",
                    return_value=idle_state,
                ),
                redirect_stdout(stdout),
            ):
                code = cli_main(["run", "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertIn("idle timeout", stdout.getvalue())

            stdout = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_rtt",
                    return_value=interrupted_state,
                ),
                redirect_stdout(stdout),
            ):
                code = cli_main(["run", "--output", str(output)])
            self.assertEqual(code, 130)
            self.assertIn("interrupted by user", stdout.getvalue())

            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.run_stop.capture_rtt",
                    side_effect=OSError("socket down"),
                ),
                redirect_stderr(stderr),
            ):
                code = cli_main(["run", "--output", str(output)])
            self.assertEqual(code, 1)
            self.assertIn("RTT run failed", stderr.getvalue())

    def test_helper_functions_cover_edge_branches(self) -> None:
        command = run_stop.build_detached_run_command(
            args=SimpleNamespace(
                host=None,
                port=1,
                connect_timeout=1.0,
                poll_interval=0.1,
                idle_timeout=5.0,
                append=True,
            ),
            workspace_root=Path("/tmp/ws"),
            output_path=Path("/tmp/ws/.dbgoracle/session.rtt"),
            state_path=Path("/tmp/ws/.dbgoracle/session.state.json"),
        )
        self.assertIn("--idle-timeout", command)
        self.assertIn("--append", command)

        with patch.dict("os.environ", {"PYTHONPATH": "existing"}, clear=False):
            env = run_stop.build_detached_run_env()
        self.assertIn("existing", env["PYTHONPATH"])

        self.assertEqual(run_stop.parse_pid({"pid": "42"}), 42)
        self.assertEqual(run_stop.parse_pid({"pid": "not-int"}), 0)
        self.assertEqual(run_stop.parse_pid({"pid": None}), 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(run_stop.RuntimeMetadataError):
                run_stop.load_runtime_metadata(path)
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(run_stop.RuntimeMetadataError):
                run_stop.load_runtime_metadata(path)

        with patch(
            "debugoracle.cli.commands.run_stop.read_process_cmdline",
            return_value="python -m debugoracle run --workspace-root /tmp",
        ):
            self.assertTrue(run_stop.is_owned_run_process(123))
        with patch(
            "debugoracle.cli.commands.run_stop.read_process_cmdline",
            return_value='python -m debugoracle "unterminated',
        ):
            self.assertFalse(run_stop.is_owned_run_process(123))

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "a.txt"
            run_stop.safe_unlink(file_path)
            file_path.write_text("x", encoding="utf-8")
            run_stop.safe_unlink(file_path)
            self.assertFalse(file_path.exists())

    def test_read_process_cmdline_ps_and_windows_fallbacks(self) -> None:
        with (
            patch("pathlib.Path.read_bytes", side_effect=OSError("no proc")),
            patch(
                "debugoracle.cli.commands.run_stop.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0, stdout="dbgoracle run", stderr=""
                ),
            ),
        ):
            self.assertEqual(run_stop.read_process_cmdline(1), "dbgoracle run")

        with (
            patch("pathlib.Path.read_bytes", side_effect=OSError("no proc")),
            patch(
                "debugoracle.cli.commands.run_stop.subprocess.run",
                side_effect=[
                    OSError("ps missing"),
                    SimpleNamespace(returncode=0, stdout="powershell run", stderr=""),
                ],
            ),
            patch(
                "debugoracle.cli.commands.run_stop.platform.system",
                return_value="Windows",
            ),
        ):
            self.assertEqual(run_stop.read_process_cmdline(1), "powershell run")


if __name__ == "__main__":
    unittest.main()
