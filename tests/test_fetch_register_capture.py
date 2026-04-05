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
from debugoracle.sources.debuggers.gdb import peripheral_registers
from debugoracle.sources.debuggers.gdb.peripheral_registers import parse_svd_definition
from debugoracle.cli import main
from debugoracle.cli.main import build_parser
from debugoracle.openocd import (
    DISCOVERY_MATCHED,
    DISCOVERY_MULTIPLE,
    DISCOVERY_NO_SESSION,
    DISCOVERY_UNREACHABLE,
    OpenOcdCandidate,
    OpenOcdDiscoveryResult,
)


FIXTURES = Path(__file__).parent / "fixtures"


class FetchRegisterCaptureTests(unittest.TestCase):
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
            self.assertIn(
                "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
                stdout,
            )

    def test_fetch_with_svd_fails_when_recent_mi_tail_ends_in_running_state(
        self,
    ) -> None:
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
            self.assertIn(
                "requires a recent halted target in the GDB/MI log", stdout + stderr
            )

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
            self.assertIn(
                "requires a recent halted target in the GDB/MI log", stdout + stderr
            )

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
            self.assertIn(
                "did not read any register values successfully", stdout + stderr
            )

    def test_fetch_with_svd_recovers_via_running_debug_session_tcl_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                with patch(
                    "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                    return_value=_discovery_result(
                        DISCOVERY_MATCHED,
                        candidate=_candidate(server.port, workspace=workspace),
                    ),
                ):
                    stdout, stderr = self._run_cli_in_workspace(
                        workspace,
                        ["fetch", "--svd-file", "test.svd", "--openocd-tcl-port", "1"],
                        env={
                            "DEBUGORACLE_OPENOCD_HOST": server.host,
                            "DEBUGORACLE_OPENOCD_PORT": "",
                        },
                        capture_stderr=True,
                    )

        self.assertIn(
            "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
            stdout,
        )
        self.assertIn("Automatic Tcl recovery: retrying fetch", stderr)
        self.assertIn(str(server.port), stderr)

    def test_fetch_with_svd_reports_that_debug_session_must_be_running_for_recovery(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd", "--openocd-tcl-port", "1"],
                )

        self.assertNotEqual(code, 0)
        message = stdout + stderr
        self.assertIn("debug session must already be running", message)
        self.assertIn("find-tcl-port --print-fetch", message)

    def test_fetch_with_svd_reports_multiple_matching_debug_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")
            candidates = (
                _candidate(4444, pid=101, workspace=workspace),
                _candidate(5555, pid=202, workspace=workspace),
            )

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(
                    status=DISCOVERY_MULTIPLE, candidates=candidates
                ),
            ):
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd", "--openocd-tcl-port", "1"],
                )

        self.assertNotEqual(code, 0)
        message = stdout + stderr
        self.assertIn("multiple running debug sessions", message)
        self.assertIn("101, 202", message)

    def test_fetch_with_svd_skips_retry_when_discovery_returns_same_endpoint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                return_value=_discovery_result(
                    DISCOVERY_UNREACHABLE, candidate=_candidate(1, workspace=workspace)
                ),
            ):
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd", "--openocd-tcl-port", "1"],
                )

        self.assertNotEqual(code, 0)
        message = stdout + stderr
        self.assertIn("same endpoint again", message)
        self.assertNotIn("Automatic Tcl recovery: retrying fetch", message)

    def test_fetch_with_svd_reports_retry_failure_after_recovered_endpoint_still_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(values={}) as server:
                with patch(
                    "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                    return_value=_discovery_result(
                        DISCOVERY_MATCHED,
                        candidate=_candidate(server.port, workspace=workspace),
                    ),
                ):
                    code, stdout, stderr = (
                        self._run_cli_expect_system_exit_in_workspace(
                            workspace,
                            [
                                "fetch",
                                "--svd-file",
                                "test.svd",
                                "--openocd-tcl-port",
                                "1",
                            ],
                            env={
                                "DEBUGORACLE_OPENOCD_HOST": server.host,
                                "DEBUGORACLE_OPENOCD_PORT": "",
                            },
                        )
                    )

        self.assertNotEqual(code, 0)
        message = stdout + stderr
        self.assertIn("Automatic Tcl recovery retried with", message)
        self.assertIn("did not read any register values successfully", message)

    def test_fetch_with_svd_nonrecoverable_failure_does_not_attempt_recovery(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                '*stopped,reason="breakpoint-hit"\n*running,thread-id="all"\n',
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session"
            ) as discovery_mock:
                code, stdout, stderr = self._run_cli_expect_system_exit_in_workspace(
                    workspace,
                    ["fetch", "--svd-file", "test.svd", "--openocd-tcl-port", "1"],
                )

        self.assertNotEqual(code, 0)
        discovery_mock.assert_not_called()
        self.assertIn(
            "requires a recent halted target in the GDB/MI log", stdout + stderr
        )

    def test_openocd_default_tcl_port_matches_documented_openocd_default(self) -> None:
        self.assertEqual(peripheral_registers.OPENOCD_DEFAULT_PORT, 6666)

    def test_fetch_with_svd_uses_default_tcl_port_when_no_override_is_given(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                previous_port = peripheral_registers.OPENOCD_DEFAULT_PORT
                peripheral_registers.OPENOCD_DEFAULT_PORT = server.port
                try:
                    stdout, _ = self._run_cli_in_workspace(
                        workspace,
                        ["fetch", "--svd-file", "test.svd"],
                        env={
                            "DEBUGORACLE_OPENOCD_HOST": server.host,
                            "DEBUGORACLE_OPENOCD_PORT": "",
                        },
                        capture_stderr=True,
                    )
                finally:
                    peripheral_registers.OPENOCD_DEFAULT_PORT = previous_port

            self.assertIn(
                "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
                stdout,
            )

    def test_fetch_with_svd_accepts_explicit_openocd_tcl_endpoint_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                stdout, _ = self._run_cli_in_workspace(
                    workspace,
                    [
                        "fetch",
                        "--svd-file",
                        "test.svd",
                        "--openocd-tcl-host",
                        server.host,
                        "--openocd-tcl-port",
                        str(server.port),
                    ],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": "127.0.0.1",
                        "DEBUGORACLE_OPENOCD_PORT": "1",
                    },
                    capture_stderr=True,
                )

            self.assertIn(
                "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
                stdout,
            )

    def test_fetch_uses_tcl_port_discovered_from_mi_log_for_workspace_default_svd(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_text = (
                'Launching gdb-server: openocd -c "gdb_port 50000" -c "tcl_port 0" -c "telnet_port 50002"\n'
                + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
            )
            (workspace / "cortex-debug-shared-mi.log").write_text(
                mi_text,
                encoding="utf-8",
            )
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "test.svd"}) + "\n",
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                mi_text = mi_text.replace("tcl_port 0", f"tcl_port {server.port}")
                (workspace / "cortex-debug-shared-mi.log").write_text(
                    mi_text, encoding="utf-8"
                )
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": "",
                    },
                    capture_stderr=True,
                )

            snapshot_path = workspace / "latest_snapshot.json"
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertIn(
            "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
            stdout,
        )
        self.assertIn(str(server.port), stderr)
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)

    def test_fetch_falls_back_to_environment_port_when_discovered_mi_tcl_port_is_unreachable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_text = (
                'Launching gdb-server: openocd -c "gdb_port 50000" -c "tcl_port 1" -c "telnet_port 50002"\n'
                + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
            )
            (workspace / "cortex-debug-shared-mi.log").write_text(
                mi_text, encoding="utf-8"
            )
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "test.svd"}) + "\n",
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                    capture_stderr=True,
                )

            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertIn(
            "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
            stdout,
        )
        self.assertIn(
            "Discovered OpenOCD Tcl port for fetch from GDB/MI log: 1", stderr
        )
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)

    def test_fetch_degrades_when_discovered_mi_tcl_port_is_unreachable_and_no_fallback_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            mi_text = (
                'Launching gdb-server: openocd -c "gdb_port 50000" -c "tcl_port 1" -c "telnet_port 50002"\n'
                + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
            )
            (workspace / "cortex-debug-shared-mi.log").write_text(
                mi_text, encoding="utf-8"
            )
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "test.svd"}) + "\n",
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_PORT": "",
                    },
                    capture_stderr=True,
                )

            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertIn("Registers: absent", stdout)
        self.assertIn(
            "Discovered OpenOCD Tcl port for fetch from GDB/MI log: 1", stderr
        )
        self.assertIn("Continuing without register capture", stderr)
        self.assertEqual(payload["sources"]["registers"]["register_count"], 0)

    def test_fetch_degrades_with_workspace_default_svd_when_no_live_session_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "test.svd"}) + "\n",
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": "127.0.0.1",
                        "DEBUGORACLE_OPENOCD_PORT": "1",
                    },
                    capture_stderr=True,
                )

            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertIn("Workspace default SVD for fetch:", stderr)
        self.assertIn("Continuing without register capture", stderr)
        self.assertIn("Registers: absent", stdout)
        self.assertEqual(payload["sources"]["registers"]["register_count"], 0)

    def test_fetch_uses_latest_launch_section_when_mi_log_contains_multiple_tcl_ports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "test.svd"}) + "\n",
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                mi_text = (
                    'Launching gdb-server: openocd -c "gdb_port 40000" -c "tcl_port 1" -c "telnet_port 40002"\n'
                    "old session noise\n"
                    'Launching gdb-server: openocd -c "gdb_port 50000" -c "tcl_port '
                    + str(server.port)
                    + '" -c "telnet_port 50002"\n'
                    + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
                )
                (workspace / "cortex-debug-shared-mi.log").write_text(
                    mi_text, encoding="utf-8"
                )
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": "",
                    },
                    capture_stderr=True,
                )

            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertIn(
            "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
            stdout,
        )
        self.assertIn(str(server.port), stderr)
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)

    def test_fetch_auto_resolves_single_workspace_svd_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "STM32L432.svd").write_text(
                _minimal_svd_text(), encoding="utf-8"
            )

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                    capture_stderr=True,
                )

            self.assertIn(
                "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
                stdout,
            )
            self.assertIn("svd-file", stderr)
            self.assertIn("STM32L432.svd", stderr)

    def test_fetch_with_ambiguous_workspace_svd_candidates_falls_back_to_raw_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "A.svd").write_text(_minimal_svd_text(), encoding="utf-8")
            (session_dir / "B.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            stdout, stderr = self._run_cli_in_workspace(
                workspace,
                ["fetch"],
                capture_stderr=True,
            )

            self.assertNotIn("Registers: present", stdout)
            self.assertIn("Multiple SVD candidates were found", stderr)
            self.assertIn("Continuing without register capture", stderr)

    def test_fetch_with_auto_discovered_svd_falls_back_to_raw_only_when_live_capture_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "STM32L432.svd").write_text(
                _minimal_svd_text(), encoding="utf-8"
            )

            with patch(
                "debugoracle.cli.commands.evidence.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["fetch"],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": "127.0.0.1",
                        "DEBUGORACLE_OPENOCD_PORT": "1",
                    },
                    capture_stderr=True,
                )

            self.assertNotIn("Registers: present", stdout)
            self.assertIn("Auto-discovered SVD", stderr)
            self.assertIn("Continuing without register capture", stderr)

    def test_fetch_ignores_openocd_tcl_flags_without_resolved_svd_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            stdout, stderr = self._run_cli_in_workspace(
                workspace,
                ["fetch", "--openocd-tcl-port", "50001"],
                capture_stderr=True,
            )

        self.assertIn("GDB: present", stdout)
        self.assertIn("Registers: absent", stdout)
        self.assertIn("no SVD file was resolved", stderr)

    def test_fetch_openocd_tcl_flags_override_environment_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "test.svd").write_text(_minimal_svd_text(), encoding="utf-8")

            with _FakeOpenOcdServer(
                values={0x40000000: "0x00000011", 0x40000004: "0x00000022"}
            ) as server:
                stdout, _ = self._run_cli_in_workspace(
                    workspace,
                    [
                        "fetch",
                        "--svd-file",
                        "test.svd",
                        "--openocd-tcl-host",
                        server.host,
                        "--openocd-tcl-port",
                        str(server.port),
                    ],
                    env={
                        "DEBUGORACLE_OPENOCD_HOST": "127.0.0.1",
                        "DEBUGORACLE_OPENOCD_PORT": "9",
                    },
                    capture_stderr=True,
                )

            self.assertIn(
                "Registers: present, 1 peripherals, 3 registers, 2 success, 0 failure, 1 skipped",
                stdout,
            )

    def test_openocd_reader_rejects_unterminated_stream_payloads(self) -> None:
        reader = peripheral_registers.OpenOcdMemoryReader()
        previous_limit = peripheral_registers.OPENOCD_MAX_RESPONSE_BYTES
        peripheral_registers.OPENOCD_MAX_RESPONSE_BYTES = 8
        try:
            reader._socket = _FakeStreamingSocket([b"boot", b"log", b"more"])
            with self.assertRaisesRegex(ValueError, "Tcl endpoint"):
                reader.read_memory(0x40000000, 32)
        finally:
            peripheral_registers.OPENOCD_MAX_RESPONSE_BYTES = previous_limit

    def test_parse_svd_definition_resolves_derived_peripherals_from_real_example(
        self,
    ) -> None:
        definition = parse_svd_definition(
            str(Path(__file__).resolve().parents[1] / "examples" / "STM32L432.svd")
        )

        peripherals = {
            peripheral.name: peripheral for peripheral in definition.peripherals
        }
        self.assertIn("GPIOC", peripherals)
        self.assertIn("GPIOE", peripherals)
        self.assertIn("DMA1", peripherals)
        self.assertIn("DMA2", peripherals)
        self.assertEqual(peripherals["GPIOE"].base_address, "0x48001000")
        self.assertEqual(peripherals["DMA2"].base_address, "0x40020400")
        self.assertGreater(len(peripherals["GPIOE"].registers), 0)
        self.assertGreater(len(peripherals["DMA2"].registers), 0)
        self.assertIn(
            "MODER", {register.name for register in peripherals["GPIOE"].registers}
        )
        self.assertIn(
            "ISR", {register.name for register in peripherals["DMA2"].registers}
        )

    def test_fetch_command_replaces_observe_and_snapshot(self) -> None:
        parser = build_parser()

        fetch_args = parser.parse_args(["fetch", "--gdb-mi", "sample.mi"])
        self.assertEqual(fetch_args.command, "fetch")

        with self.assertRaises(SystemExit):
            parser.parse_args(["observe"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["snapshot"])

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

    def test_snapshot_keeps_full_embedded_rtt_when_recent_window_is_trimmed(
        self,
    ) -> None:
        bundle = build_bundle_from_text(
            "^done\n", "line one\nline two\nline three\n", rtt_window=2
        )

        self.assertEqual(bundle.provenance["rtt_line_count"], 2)
        self.assertEqual(
            bundle.sources.rtt.lines, ["line one", "line two", "line three"]
        )
        self.assertEqual(
            bundle.sources.rtt.raw_text, "line one\nline two\nline three\n"
        )

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


def _candidate(
    port: int, *, pid: int = 1234, workspace: Path | None = None
) -> OpenOcdCandidate:
    return OpenOcdCandidate(
        pid=pid,
        argv=("openocd", "-c", f"tcl_port {port}"),
        cwd=str(workspace) if workspace is not None else None,
        host="127.0.0.1",
        tcl_port=port,
        gdb_port=None,
        telnet_port=None,
    )


def _discovery_result(
    status: str, *, candidate: OpenOcdCandidate | None = None
) -> OpenOcdDiscoveryResult:
    candidates = (candidate,) if candidate is not None else ()
    return OpenOcdDiscoveryResult(
        status=status, candidate=candidate, candidates=candidates
    )


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


class _FakeStreamingSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.sent_commands: list[bytes] = []

    def sendall(self, payload: bytes) -> None:
        self.sent_commands.append(payload)

    def recv(self, _: int) -> bytes:
        if not self._chunks:
            raise AssertionError(
                "reader kept consuming an unterminated stream past the safety limit"
            )
        return self._chunks.pop(0)


if __name__ == "__main__":
    unittest.main()
