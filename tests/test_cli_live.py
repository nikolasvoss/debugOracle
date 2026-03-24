from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.cli import main
from debugoracle.openocd import DISCOVERY_MATCHED, DISCOVERY_NO_SESSION, OpenOcdCandidate, OpenOcdDiscoveryResult
FIXTURES = Path(__file__).parent / "fixtures"


class DebugOracleLiveCliTests(unittest.TestCase):
    def test_legacy_cli_main_boundary_remains_callable(self) -> None:
        import debugoracle.cli as cli_module

        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir)
            output = self._run_cli_with(cli_module.main, ["status", "--workspace-root", tmpdir])

        self.assertIn("DebugOracle Session Status", output)
        self.assertIn("Health: healthy", output)

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

    def test_status_discovers_workspace_root_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            save_bundle(bundle, str(workspace / "latest_snapshot.json"))
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
                os.chdir(tmpdir)
                output = self._run_cli(["status"])
            finally:
                os.chdir(previous)

        self.assertIn("DebugOracle Session Status", output)
        self.assertIn("Health: healthy", output)
        self.assertIn("Snapshot ID: snap-", output)

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

    def test_status_command_reports_prepared_attach_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_attach_workspace(Path(tmpdir))
            with patch(
                "debugoracle.session.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                output = self._run_cli(["status", "--workspace-root", tmpdir])

        self.assertIn("Golden Path: prepared", output)
        self.assertIn("Next Human Action: Start `DebugOracle: Attach STM32`", output)

    def test_status_command_reports_live_attach_workspace_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir)
            self._write_attach_workspace(Path(tmpdir))
            candidate = OpenOcdCandidate(
                pid=1234,
                argv=("openocd", "-c", "tcl_port 50001"),
                cwd=tmpdir,
                host="127.0.0.1",
                tcl_port=50001,
                gdb_port=None,
                telnet_port=None,
            )
            with patch(
                "debugoracle.session.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_MATCHED, candidate=candidate),
            ):
                output = self._run_cli(["status", "--workspace-root", tmpdir, "--format", "json"])

        payload = __import__("json").loads(output)
        self.assertEqual(payload["readiness"]["state"], "live")
        self.assertEqual(payload["readiness"]["launch_config_name"], "DebugOracle: Attach STM32")

    def test_status_command_keeps_attach_workspace_degraded_when_live_proof_is_weak(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_workspace(tmpdir)
            self._write_attach_workspace(Path(tmpdir))
            with patch(
                "debugoracle.session.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                output = self._run_cli(["status", "--workspace-root", tmpdir])

        self.assertIn("Golden Path: degraded", output)
        self.assertIn("not trusted as live yet", output)

    def _run_cli(self, argv: list[str]) -> str:
        return self._run_cli_with(main, argv)

    def _run_cli_with(self, entrypoint: object, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = entrypoint(argv)
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

    def _write_attach_workspace(self, workspace: Path) -> None:
        vscode_dir = workspace / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        (vscode_dir / "settings.json").write_text(
            "{\n"
            '  "debugoracle.workspaceSetupMode": "attach",\n'
            '  "debugoracle.launchConfigName": "DebugOracle: Attach STM32",\n'
            '  "debugoracle.launchConfigRole": "golden-path-attach"\n'
            "}\n",
            encoding="utf-8",
        )
        (vscode_dir / "launch.json").write_text(
            "{\n"
            '  "version": "0.2.0",\n'
            '  "configurations": [\n'
            '    {\n'
            '      "name": "DebugOracle: Attach STM32",\n'
            '      "type": "cortex-debug",\n'
            '      "request": "launch",\n'
            '      "debugoracleRole": "golden-path-attach",\n'
            '      "preLaunchTask": "DebugOracle: Prelaunch",\n'
            '      "postDebugTask": "DebugOracle: Stop RTT run"\n'
            '    }\n'
            '  ]\n'
            "}\n",
            encoding="utf-8",
        )
        (vscode_dir / "tasks.json").write_text(
            "{\n"
            '  "version": "2.0.0",\n'
            '  "tasks": [\n'
            '    {"label": "DebugOracle: Prelaunch"},\n'
            '    {"label": "DebugOracle: Stop RTT run"}\n'
            '  ]\n'
            "}\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
