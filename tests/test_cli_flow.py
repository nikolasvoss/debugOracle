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

from debugoracle.artifacts.repository import save_artifact
from debugoracle.builder import build_bundle_from_files
from debugoracle.cli.commands.evidence import _warning_for_stderr
from debugoracle.cli.commands.find_tcl_port import OpenOcdCandidate
from debugoracle.cli.main import build_parser, main
from debugoracle.readiness import ReadinessState, collect_host_readiness


FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_OPENOCD_VALUES = {
    0x48000000: "0xaaaaaaaa",
    0x48000010: "0x00000001",
}


class DebugOracleCliTests(unittest.TestCase):
    def test_host_readiness_detects_supported_cortex_debug_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            extension = home / ".vscode" / "extensions" / "marus25.cortex-debug-1.12.1"
            extension.mkdir(parents=True)

            report = collect_host_readiness(path="", home=home)

        cortex_debug = next(item for item in report.items if item.key == "cortex_debug")
        self.assertEqual(cortex_debug.state, ReadinessState.READY)

    def test_doctor_host_reports_read_only_json_readiness(self) -> None:
        stdout, stderr, exit_code = self._run_cli_capture(
            ["doctor", "host", "--format", "json"]
        )

        payload = json.loads(stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["scope"], "host")
        self.assertIn(payload["status"], {"ready", "needs_host_dependency", "blocked"})
        self.assertEqual(
            [item["key"] for item in payload["items"]],
            [
                "platform",
                "python",
                "pipx",
                "openocd",
                "arm_gdb",
                "vscode",
                "cortex_debug",
            ],
        )
        self.assertTrue(
            all(item["requires_approval"] is False for item in payload["items"])
        )

    def test_workspace_plan_reports_ambiguous_elf_candidates_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "build").mkdir()
            (workspace / "build" / "app-a.elf").write_bytes(b"elf-a")
            (workspace / "build" / "app-b.elf").write_bytes(b"elf-b")
            (workspace / "board.svd").write_text("<device />\n", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "workspace",
                    "plan",
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "needs_user_choice")
        self.assertEqual(
            payload["candidates"]["executables"],
            [
                str(workspace / "build" / "app-a.elf"),
                str(workspace / "build" / "app-b.elf"),
            ],
        )
        self.assertEqual(
            payload["candidates"]["svd_files"], [str(workspace / "board.svd")]
        )
        self.assertFalse((workspace / ".dbgoracle").exists())

    def test_workspace_plan_ignores_elf_outside_known_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "vendor").mkdir()
            (workspace / "vendor" / "ignored.elf").write_bytes(b"elf")
            (workspace / "build").mkdir()
            (workspace / "build" / "app.elf").write_bytes(b"elf")

            stdout, _stderr, exit_code = self._run_cli_capture(
                [
                    "workspace",
                    "plan",
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(
            payload["candidates"]["executables"], [str(workspace / "build" / "app.elf")]
        )

    def test_workspace_plan_reports_truncation_at_directory_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            build = workspace / "build"
            build.mkdir()
            for index in range(4097):
                (build / f"part-{index}.elf").write_bytes(b"elf")

            stdout, _stderr, exit_code = self._run_cli_capture(
                [
                    "workspace",
                    "plan",
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["status"], "blocked")

    def test_session_doctor_reports_missing_local_config_without_socket_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "socket.create_connection", side_effect=AssertionError("socket used")
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "session",
                        "doctor",
                        "--workspace-root",
                        str(workspace),
                        "--format",
                        "json",
                    ]
                )

        payload = json.loads(stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["scope"], "session")
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["target_contact"], "not_attempted")
        self.assertIn("settings", payload["checks"])
        self.assertIn("launch", payload["checks"])

    def test_session_doctor_accepts_jsonc_and_rejects_missing_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            vscode = workspace / ".vscode"
            vscode.mkdir()
            (vscode / "settings.json").write_text(
                '{\n  // DebugOracle settings\n  "debugoracle.executable": "build/app.elf",\n'
                '  "debugoracle.miLogPath": "${workspaceFolder}/.dbgoracle/session.mi",\n}\n',
                encoding="utf-8",
            )
            (vscode / "launch.json").write_text(
                '{"configurations": [{"type": "cortex-debug", "configFiles": ["board.cfg"]}]}\n',
                encoding="utf-8",
            )
            (vscode / "tasks.json").write_text(
                '{"version": "2.0.0"}\n', encoding="utf-8"
            )

            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "session",
                    "doctor",
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["checks"]["settings"], "ready")
        self.assertEqual(payload["checks"]["executable"], "missing")
        self.assertEqual(payload["status"], "blocked")

    def test_session_doctor_rejects_workspace_config_paths_outside_workspace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            vscode = workspace / ".vscode"
            vscode.mkdir()
            (vscode / "settings.json").write_text(
                '{"debugoracle.executable": "/etc/passwd", "debugoracle.miLogPath": "/tmp/session.mi"}\n',
                encoding="utf-8",
            )
            (vscode / "launch.json").write_text(
                '{"configurations": []}\n', encoding="utf-8"
            )
            (vscode / "tasks.json").write_text(
                '{"version": "2.0.0"}\n', encoding="utf-8"
            )

            stdout, _stderr, exit_code = self._run_cli_capture(
                [
                    "session",
                    "doctor",
                    "--workspace-root",
                    str(workspace),
                    "--format",
                    "json",
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["checks"]["executable"], "outside_workspace")
        self.assertEqual(payload["checks"]["mi_log_destination"], "outside_workspace")
        self.assertEqual(payload["status"], "blocked")

    def test_fetch_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["fetch"])

        self.assertEqual(parsed.command, "fetch")

    def test_fetch_command_parses_repeatable_mem_selectors(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            ["fetch", "--mem", "0x20002000:4", "--mem", "8192:2"]
        )

        self.assertEqual(parsed.command, "fetch")
        self.assertEqual(parsed.mem, ["0x20002000:4", "8192:2"])

    def test_find_tcl_port_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            ["find-tcl-port", "--workspace-root", ".", "--print-fetch"]
        )

        self.assertEqual(parsed.command, "find-tcl-port")
        self.assertTrue(parsed.print_fetch)

    def test_guard_openocd_launch_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["guard-openocd-launch", "--workspace-root", "."])

        self.assertEqual(parsed.command, "guard-openocd-launch")

    def test_find_tcl_port_prints_fetch_command_for_workspace_default_svd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "${workspaceFolder}/device.svd"})
                + "\n",
                encoding="utf-8",
            )
            (workspace / "device.svd").write_text("<device />\n", encoding="utf-8")
            candidate = OpenOcdCandidate(
                pid=1234,
                argv=("openocd", "-c", "gdb_port 50000", "-c", "tcl_port 50001"),
                cwd=str(workspace),
                host="127.0.0.1",
                tcl_port=50001,
                gdb_port=50000,
                telnet_port=None,
            )

            with (
                patch(
                    "debugoracle.cli.commands.find_tcl_port.discover_openocd_candidates",
                    return_value=[candidate],
                ),
                patch(
                    "debugoracle.cli.commands.find_tcl_port.is_tcp_endpoint_reachable",
                    return_value=True,
                ),
            ):
                stdout, stderr = self._run_cli_in_workspace(
                    workspace,
                    ["find-tcl-port", "--workspace-root", ".", "--print-fetch"],
                    capture_stderr=True,
                )

        self.assertIn("OpenOCD Tcl port: 50001", stdout)
        self.assertIn("Run this:", stdout)
        self.assertIn("dbgoracle fetch --workspace-root", stdout)
        self.assertIn("--openocd-tcl-port 50001", stdout)
        self.assertIn("Workspace default SVD for fetch:", stderr)

    def test_find_tcl_port_succeeds_without_svd_and_prints_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            candidate = OpenOcdCandidate(
                pid=1234,
                argv=("openocd", "-c", "tcl_port 50001"),
                cwd=str(workspace),
                host="127.0.0.1",
                tcl_port=50001,
                gdb_port=None,
                telnet_port=None,
            )

            with (
                patch(
                    "debugoracle.cli.commands.find_tcl_port.discover_openocd_candidates",
                    return_value=[candidate],
                ),
                patch(
                    "debugoracle.cli.commands.find_tcl_port.is_tcp_endpoint_reachable",
                    return_value=True,
                ),
            ):
                stdout, stderr, exit_code = self._run_cli_capture_in_workspace(
                    workspace,
                    ["find-tcl-port", "--workspace-root", ".", "--print-fetch"],
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("OpenOCD Tcl port: 50001", stdout)
        self.assertIn("Resolved SVD: none", stdout)
        self.assertIn("Fetch command: not available", stderr)

    def test_find_tcl_port_fails_clearly_when_multiple_sessions_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            candidates = [
                OpenOcdCandidate(
                    pid=100,
                    argv=("openocd", "-c", "tcl_port 40001"),
                    cwd=None,
                    host="127.0.0.1",
                    tcl_port=40001,
                    gdb_port=None,
                    telnet_port=None,
                ),
                OpenOcdCandidate(
                    pid=200,
                    argv=("openocd", "-c", "tcl_port 50001"),
                    cwd=None,
                    host="127.0.0.1",
                    tcl_port=50001,
                    gdb_port=None,
                    telnet_port=None,
                ),
            ]

            with patch(
                "debugoracle.cli.commands.find_tcl_port.discover_openocd_candidates",
                return_value=candidates,
            ):
                stdout, stderr, exit_code = self._run_cli_capture_in_workspace(
                    workspace,
                    ["find-tcl-port", "--workspace-root", "."],
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Multiple active OpenOCD sessions match", stderr)
        self.assertIn("--pid", stderr)

    def test_init_workspace_requires_openocd_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--svd-file",
                    "STM32L432.svd",
                    "--with-rtt",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("--openocd-config", stderr)
        self.assertIn("cannot guess your OpenOCD setup", stderr)
        self.assertIn("interface/*.cfg", stderr)
        self.assertIn("target/*.cfg", stderr)
        self.assertIn("dbgoracle init-workspace", stderr)
        self.assertIn("configFiles", stderr)
        self.assertFalse((workspace / ".vscode").exists())
        self.assertFalse((workspace / ".dbgoracle").exists())

    def test_install_cli_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            ["install-cli", "--manifest-url", "https://example.com/manifest.json"]
        )

        self.assertEqual(parsed.command, "install_cli")
        self.assertEqual(parsed.manifest_url, "https://example.com/manifest.json")

    def test_uninstall_cli_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["uninstall-cli", "--force-legacy-path-cleanup"])

        self.assertEqual(parsed.command, "uninstall_cli")
        self.assertTrue(parsed.force_legacy_path_cleanup)

    def test_internal_installer_commands_are_hidden_from_top_level_help(self) -> None:
        parser = build_parser()

        help_text = parser.format_help()

        self.assertNotIn("install-cli", help_text)
        self.assertNotIn("uninstall-cli", help_text)
        self.assertNotIn("==SUPPRESS==", help_text)

    def test_uninstall_cli_rejects_manifest_url(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit) as error:
            with redirect_stderr(io.StringIO()) as stderr:
                parser.parse_args(
                    [
                        "uninstall-cli",
                        "--manifest-url",
                        "https://example.com/manifest.json",
                    ]
                )
        self.assertEqual(error.exception.code, 2)
        self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_init_workspace_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            [
                "init-workspace",
                "--workspace-root",
                ".",
                "--executable",
                "build/app.elf",
                "--openocd-config",
                "interface/stlink.cfg",
            ]
        )
        self.assertEqual(parsed.command, "init_workspace")

    def test_init_workspace_attach_mode_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            [
                "init-workspace",
                "--workspace-root",
                ".",
                "--executable",
                "build/app.elf",
                "--attach",
                "--openocd-config",
                "interface/stlink.cfg",
            ]
        )

        self.assertTrue(parsed.attach)
        self.assertEqual(parsed.command, "init_workspace")

    def test_init_workspace_help_marks_openocd_config_as_required(self) -> None:
        parser = build_parser()
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as error:
            with redirect_stdout(stdout):
                parser.parse_args(["init-workspace", "--help"])

        self.assertEqual(error.exception.code, 0)
        self.assertIn("Required OpenOCD config file", stdout.getvalue())

    def test_removed_legacy_commands_are_rejected(self) -> None:
        parser = build_parser()
        for argv in (["observe"], ["snapshot"], ["prompt"]):
            with self.assertRaises(SystemExit) as error:
                with redirect_stderr(io.StringIO()) as stderr:
                    parser.parse_args(argv)
            self.assertEqual(error.exception.code, 2)
            self.assertIn("invalid choice", stderr.getvalue())

    def test_init_workspace_creates_fresh_workspace_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--executable",
                        "build/app.elf",
                        "--openocd-config",
                        "interface/stlink.cfg",
                        "--openocd-config",
                        "target/stm32l4x.cfg",
                    ]
                )

            settings_path = workspace / ".vscode" / "settings.json"
            launch_path = workspace / ".vscode" / "launch.json"
            tasks_path = workspace / ".vscode" / "tasks.json"
            session_dir = workspace / ".dbgoracle"

            self.assertEqual(exit_code, 0)
            self.assertTrue(session_dir.is_dir())
            self.assertTrue(settings_path.is_file())
            self.assertTrue(launch_path.is_file())
            self.assertTrue(tasks_path.is_file())

            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(settings["debugoracle.executable"], "build/app.elf")
            self.assertEqual(
                settings["debugoracle.openocdConfigFiles"],
                ["interface/stlink.cfg", "target/stm32l4x.cfg"],
            )
            self.assertEqual(
                settings["debugoracle.miLogPath"],
                "${workspaceFolder}/.dbgoracle/cortex-debug-shared-mi.log",
            )
            launch_text = launch_path.read_text(encoding="utf-8")
            self.assertIn('"configFiles": [', launch_text)
            self.assertIn('"interface/stlink.cfg"', launch_text)
            self.assertIn('"target/stm32l4x.cfg"', launch_text)
            self.assertIn('"preLaunchTask": "Prepare debug logs"', launch_text)
            self.assertNotIn(
                '"postDebugTask": "DebugOracle: Stop RTT run"', launch_text
            )
            self.assertIn("init-workspace", stdout)
            self.assertEqual(stderr, "")

    def test_init_workspace_with_rtt_enables_rtt_commands_in_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--executable",
                        "build/app.elf",
                        "--openocd-config",
                        "interface/stlink.cfg",
                        "--openocd-config",
                        "target/stm32l4x.cfg",
                        "--with-rtt",
                    ]
                )

            launch_text = (workspace / ".vscode" / "launch.json").read_text(
                encoding="utf-8"
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn('"preLaunchTask": "DebugOracle: Prelaunch"', launch_text)
        self.assertIn('"postDebugTask": "DebugOracle: Stop RTT run"', launch_text)
        self.assertIn(
            '"monitor rtt setup 0x20000000 0x1000 \\"SEGGER RTT\\""', launch_text
        )
        self.assertIn('"monitor rtt start"', launch_text)
        self.assertIn(
            '"monitor rtt server start ${config:debugoracle.rttPort} 0"', launch_text
        )
        self.assertNotIn(
            '// "monitor rtt setup 0x20000000 0x1000 \\"SEGGER RTT\\""', launch_text
        )
        self.assertIn("init-workspace", stdout)

    def test_init_workspace_with_custom_rtt_port_keeps_tasks_and_launch_in_sync(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--executable",
                        "build/app.elf",
                        "--openocd-config",
                        "interface/stlink.cfg",
                        "--openocd-config",
                        "target/stm32l4x.cfg",
                        "--with-rtt",
                        "--rtt-port",
                        "9090",
                    ]
                )

            settings = json.loads(
                (workspace / ".vscode" / "settings.json").read_text(encoding="utf-8")
            )
            launch_text = (workspace / ".vscode" / "launch.json").read_text(
                encoding="utf-8"
            )
            tasks_text = (workspace / ".vscode" / "tasks.json").read_text(
                encoding="utf-8"
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(settings["debugoracle.rttPort"], "9090")
        self.assertIn("${config:debugoracle.rttPort}", launch_text)
        self.assertIn("--port ${config:debugoracle.rttPort}", tasks_text)
        self.assertNotIn("monitor rtt server start 60001 0", launch_text)
        self.assertIn("init-workspace", stdout)

    def test_init_workspace_resolves_executable_relative_to_workspace_root(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            tempfile.TemporaryDirectory() as otherdir,
        ):
            workspace = Path(tmpdir)
            (workspace / "build").mkdir()
            (workspace / "build" / "app.elf").write_text("elf", encoding="utf-8")
            previous = os.getcwd()
            try:
                os.chdir(otherdir)
                with patch(
                    "debugoracle.cli.commands.init_workspace.shutil.which",
                    return_value="/usr/bin/openocd",
                ):
                    stdout, stderr, exit_code = self._run_cli_capture(
                        [
                            "init-workspace",
                            "--workspace-root",
                            str(workspace),
                            "--executable",
                            "build/app.elf",
                            "--openocd-config",
                            "interface/stlink.cfg",
                            "--format",
                            "json",
                        ]
                    )
            finally:
                os.chdir(previous)

            payload = json.loads(stdout)

        self.assertEqual(exit_code, 0)
        executable = next(
            item
            for item in payload["dependency_checks"]
            if item["name"] == "executable"
        )
        self.assertEqual(executable["status"], "available")
        cortex_debug = next(
            item
            for item in payload["dependency_checks"]
            if item["name"] == "cortex-debug"
        )
        self.assertIn("minimum supported version 1.12.1", cortex_debug["detail"])
        self.assertEqual(stderr, "")

    def test_init_workspace_returns_failed_json_when_openocd_config_is_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["workspace_root"], str(workspace.resolve()))
        self.assertEqual(payload["created_files"], [])
        self.assertEqual(payload["blocked_files"], [])
        self.assertEqual(payload["required_actions"][0]["path"], "--openocd-config")
        self.assertIn(
            "cannot guess your OpenOCD setup",
            payload["required_actions"][0]["fragment"],
        )
        self.assertEqual(payload["dependency_checks"], [])
        self.assertEqual(stderr, "")

    def test_init_workspace_returns_partial_json_when_existing_settings_block_automation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            vscode_dir = workspace / ".vscode"
            vscode_dir.mkdir(parents=True)
            (vscode_dir / "settings.json").write_text("{}\n", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--openocd-config",
                    "interface/stlink.cfg",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(payload["status"], "partial")
            self.assertIn(str(vscode_dir / "settings.json"), payload["blocked_files"])
            self.assertEqual(
                payload["required_actions"][0]["path"],
                str(vscode_dir / "settings.json"),
            )
            self.assertIn(
                "debugoracle.executable", payload["required_actions"][0]["fragment"]
            )
            self.assertTrue((workspace / ".vscode" / "launch.json").is_file())
            self.assertTrue((workspace / ".vscode" / "tasks.json").is_file())
            self.assertTrue((workspace / ".dbgoracle").is_dir())
            self.assertEqual(stderr, "")

    def test_init_workspace_creates_optional_input_folder_and_owned_ignore_rules(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / ".gitignore").write_text("existing-rule\n", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--openocd-config",
                    "interface/stlink.cfg",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            gitignore = (workspace / ".gitignore").read_text(encoding="utf-8")
            input_exists = (workspace / "debugoracle-input").is_dir()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(input_exists)
        self.assertIn("existing-rule\n", gitignore)
        self.assertIn("# DebugOracle workspace files\n", gitignore)
        self.assertIn("debugoracle-input/\n", gitignore)
        self.assertIn(".dbgoracle/\n", gitignore)
        self.assertIn(str(workspace / "debugoracle-input"), payload["created_files"])

    def test_init_workspace_rejects_symlinked_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            outside = Path(tmpdir) / "outside-gitignore"
            workspace.mkdir()
            outside.write_text("outside-rule\n", encoding="utf-8")
            (workspace / ".gitignore").symlink_to(outside)

            _stdout, _stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--openocd-config",
                    "interface/stlink.cfg",
                    "--format",
                    "json",
                ]
            )

            outside_content = outside.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertEqual(outside_content, "outside-rule\n")

    def test_init_workspace_attach_mode_returns_agent_merge_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--attach",
                    "--openocd-config",
                    "interface/stlink.cfg",
                    "--openocd-config",
                    "target/stm32l4x.cfg",
                    "--with-rtt",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["mode"], "attach")
        self.assertEqual(payload["merge_strategy"], "agent")
        self.assertEqual(payload["launch_config_name"], "DebugOracle: Attach STM32")
        self.assertIn(
            "Merge the DebugOracle attach fragments", payload["next_human_action"]
        )
        self.assertEqual(
            payload["blocked_files"],
            [
                str(workspace / ".vscode" / "settings.json"),
                str(workspace / ".vscode" / "launch.json"),
                str(workspace / ".vscode" / "tasks.json"),
            ],
        )
        self.assertEqual(payload["created_files"], [])
        self.assertEqual(stderr, "")
        self.assertIn(
            '"debugoracle.workspaceSetupMode": "attach"',
            payload["required_actions"][0]["fragment"],
        )
        self.assertIn(
            '"name": "DebugOracle: Attach STM32"',
            payload["required_actions"][1]["fragment"],
        )
        self.assertIn(
            '"debugoracleRole": "golden-path-attach"',
            payload["required_actions"][1]["fragment"],
        )
        self.assertIn(
            '"label": "DebugOracle: Prelaunch"',
            payload["required_actions"][2]["fragment"],
        )
        self.assertIn(
            '"label": "DebugOracle: Guard Attach Launch"',
            payload["required_actions"][2]["fragment"],
        )
        self.assertFalse((workspace / ".vscode").exists())

    def test_init_workspace_attach_mode_without_rtt_still_wires_prelaunch_guard(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--attach",
                    "--openocd-config",
                    "interface/stlink.cfg",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        self.assertIn(
            '"preLaunchTask": "DebugOracle: Prelaunch"',
            payload["required_actions"][1]["fragment"],
        )
        self.assertIn(
            '"label": "DebugOracle: Guard Attach Launch"',
            payload["required_actions"][2]["fragment"],
        )
        self.assertNotIn(
            "DebugOracle: Start RTT run", payload["required_actions"][2]["fragment"]
        )

    def test_init_workspace_attach_mode_keeps_existing_launch_file_untouched(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            vscode_dir = workspace / ".vscode"
            vscode_dir.mkdir(parents=True)
            launch_path = vscode_dir / "launch.json"
            original = '{"version":"0.2.0","configurations":[{"name":"User Debug"}]}\n'
            launch_path.write_text(original, encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--attach",
                    "--openocd-config",
                    "interface/stlink.cfg",
                    "--format",
                    "json",
                ]
            )
            payload = json.loads(stdout)

            self.assertEqual(exit_code, 2)
            self.assertEqual(payload["mode"], "attach")
            self.assertEqual(launch_path.read_text(encoding="utf-8"), original)
            self.assertIn(str(launch_path), payload["blocked_files"])
            self.assertEqual(stderr, "")

    def test_init_workspace_text_output_includes_required_fragment_for_blocked_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            vscode_dir = workspace / ".vscode"
            vscode_dir.mkdir(parents=True)
            (vscode_dir / "settings.json").write_text("{}\n", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--executable",
                    "build/app.elf",
                    "--openocd-config",
                    "interface/stlink.cfg",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("Required actions:", stdout)
        self.assertIn('"debugoracle.executable": "build/app.elf"', stdout)
        self.assertEqual(stderr, "")

    def test_init_workspace_writes_workspace_default_svd_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--executable",
                        "build/app.elf",
                        "--openocd-config",
                        "interface/stlink.cfg",
                        "--svd-file",
                        "boards/sample.svd",
                    ]
                )

            settings = json.loads(
                (workspace / ".vscode" / "settings.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            settings["debugoracle.svdFile"], str(workspace / "boards" / "sample.svd")
        )
        self.assertEqual(stderr, "")
        self.assertIn("init-workspace", stdout)

    def test_init_workspace_expands_workspace_token_in_svd_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--executable",
                        "build/app.elf",
                        "--openocd-config",
                        "interface/stlink.cfg",
                        "--svd-file",
                        "${workspaceFolder}/boards/sample.svd",
                    ]
                )

            settings = json.loads(
                (workspace / ".vscode" / "settings.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            settings["debugoracle.svdFile"], str(workspace / "boards" / "sample.svd")
        )
        self.assertEqual(stderr, "")
        self.assertIn("init-workspace", stdout)

    def test_init_workspace_reports_missing_openocd_as_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value=None,
            ):
                stdout, stderr, exit_code = self._run_cli_capture(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--executable",
                        "build/app.elf",
                        "--openocd-config",
                        "interface/stlink.cfg",
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "partial")
        openocd = next(
            item for item in payload["dependency_checks"] if item["name"] == "openocd"
        )
        self.assertEqual(openocd["status"], "missing")
        self.assertEqual(stderr, "")

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
            self.assertIn("dbgoracle report --workspace-root .", stdout)
            self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_fetch_next_commands_use_portable_workspace_root(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            tempfile.TemporaryDirectory() as otherdir,
        ):
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
                stdout, _ = self._run_cli(
                    ["fetch", "--workspace-root", tmpdir], capture_stderr=True
                )
            finally:
                os.chdir(previous)

        self.assertIn("dbgoracle report --workspace-root .", stdout)
        self.assertNotIn(
            f"dbgoracle report --workspace-root {workspace.resolve()}", stdout
        )

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

    def test_report_vars_outputs_grouped_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--vars"]
            )

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
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--gdb"]
            )

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "gdb"})
        self.assertIn("events", payload["gdb"])
        self.assertTrue(payload["metadata"]["snapshot_id"].startswith("snap-"))
        self.assertEqual(payload["metadata"]["source_availability"]["gdb"], "present")

    def test_report_rtt_outputs_rtt_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--rtt"]
            )

        payload = json.loads(output)
        self.assertEqual(set(payload.keys()), {"trust", "metadata", "rtt"})
        self.assertIn("lines", payload["rtt"])
        self.assertEqual(payload["metadata"]["source_availability"]["rtt"], "present")

    def test_report_verbose_outputs_composite_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--verbose"]
            )

        payload = json.loads(output)
        self.assertIn("summary", payload)
        self.assertIn("variables", payload)
        self.assertIn("gdb", payload)
        self.assertIn("rtt", payload)
        self.assertIn("provenance", payload)

    def test_fetch_uses_workspace_default_svd_file_from_vscode_settings(self) -> None:
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
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": str(FIXTURES / "sample.svd")})
                + "\n",
                encoding="utf-8",
            )

            with _FakeOpenOcdServer(values=DEFAULT_OPENOCD_VALUES) as server:
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

        self.assertIn("Registers: present", stdout)
        self.assertIn("Workspace default SVD for fetch:", stderr)
        self.assertEqual(
            payload["sources"]["registers"]["device_name"], "STM32L432KCTest"
        )

    def test_fetch_reads_workspace_default_svd_from_jsonc_with_url_string(self) -> None:
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
            (workspace / ".vscode").mkdir()
            (workspace / ".vscode" / "settings.json").write_text(
                "{\n"
                "  // workspace metadata\n"
                '  "debugoracle.svdFile": "' + str(FIXTURES / "sample.svd") + '",\n'
                '  "test.url": "https://example.com/debug",\n'
                "}\n",
                encoding="utf-8",
            )

            with _FakeOpenOcdServer(values=DEFAULT_OPENOCD_VALUES) as server:
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

        self.assertIn("Registers: present", stdout)
        self.assertIn("Workspace default SVD for fetch:", stderr)
        self.assertEqual(
            payload["sources"]["registers"]["device_name"], "STM32L432KCTest"
        )

    def test_fetch_expands_workspace_folder_token_for_workspace_default_svd(
        self,
    ) -> None:
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
            (workspace / ".vscode").mkdir()
            (workspace / "STM32L432.svd").write_text(
                (FIXTURES / "sample.svd").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / ".vscode" / "settings.json").write_text(
                json.dumps({"debugoracle.svdFile": "${workspaceFolder}/STM32L432.svd"})
                + "\n",
                encoding="utf-8",
            )

            with _FakeOpenOcdServer(values=DEFAULT_OPENOCD_VALUES) as server:
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

        self.assertIn("Registers: present", stdout)
        self.assertIn(str(workspace / "STM32L432.svd"), stderr)
        self.assertEqual(
            payload["sources"]["registers"]["device_name"], "STM32L432KCTest"
        )

    def test_fetch_with_svd_captures_register_values_and_prints_register_guidance(
        self,
    ) -> None:
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

            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertIn("Registers: present", stdout)
        self.assertIn("dbgoracle report --workspace-root . --regs-list", stdout)
        self.assertEqual(
            payload["sources"]["registers"]["device_name"], "STM32L432KCTest"
        )
        self.assertEqual(payload["sources"]["registers"]["register_count"], 4)
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)
        self.assertEqual(payload["sources"]["registers"]["skipped_count"], 2)
        self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_report_regs_list_outputs_captured_peripherals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(
                Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd"
            )
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--regs-list"]
            )

        payload = json.loads(output)
        self.assertEqual(payload["registers_list"]["device_name"], "STM32L432KCTest")
        self.assertEqual(
            [item["name"] for item in payload["registers_list"]["peripherals"]],
            ["GPIOA", "RCC"],
        )
        self.assertEqual(
            payload["registers_list"]["peripherals"][0]["success_count"], 2
        )
        self.assertEqual(
            payload["registers_list"]["peripherals"][0]["failure_count"], 0
        )
        self.assertEqual(
            payload["registers_list"]["peripherals"][1]["skipped_count"], 2
        )

    def test_report_regs_list_peripheral_outputs_registers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(
                Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd"
            )
            output = self._run_cli(
                [
                    "report",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--regs-list",
                    "GPIOA",
                ]
            )

        payload = json.loads(output)
        self.assertEqual(payload["registers_list"]["peripheral"], "GPIOA")
        self.assertEqual(
            [item["name"] for item in payload["registers_list"]["registers"]],
            ["MODER", "IDR"],
        )
        self.assertEqual(
            [item["read_status"] for item in payload["registers_list"]["registers"]],
            ["success", "success"],
        )

    def test_report_regs_outputs_filtered_register_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(
                Path(tmpdir) / "latest_snapshot.json", svd_file=FIXTURES / "sample.svd"
            )
            output = self._run_cli(
                [
                    "report",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--regs",
                    "GPIOA:MODER",
                    "RCC",
                ]
            )

        payload = json.loads(output)
        self.assertEqual(
            [item["name"] for item in payload["registers"]["peripherals"]],
            ["GPIOA", "RCC"],
        )
        self.assertEqual(
            payload["registers"]["peripherals"][0]["registers"][0]["name"], "MODER"
        )
        self.assertEqual(
            payload["registers"]["peripherals"][0]["registers"][0]["read_status"],
            "success",
        )
        self.assertEqual(
            payload["registers"]["peripherals"][0]["registers"][0]["value_hex"],
            "0xaaaaaaaa",
        )
        self.assertEqual(
            payload["registers"]["peripherals"][1]["registers"][0]["read_status"],
            "skipped",
        )

    def test_report_regs_list_fails_when_register_data_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(
                ["report", "--snapshot-file", str(snapshot_path), "--regs-list"]
            )

        self.assertNotEqual(code, 0)
        self.assertIn("embedded register source", stdout + stderr)

    def test_report_rejects_invalid_register_selector(self) -> None:
        code, stdout, stderr = self._run_cli_expect_system_exit(
            ["report", "--regs", "GPIOA:"]
        )
        self.assertNotEqual(code, 0)
        self.assertIn("invalid register selector", stdout + stderr)

    def test_report_rejects_invalid_mem_selector(self) -> None:
        code, stdout, stderr = self._run_cli_expect_system_exit(
            ["report", "--mem", "GPIOA:"]
        )
        self.assertNotEqual(code, 0)
        self.assertIn("invalid memory selector", (stdout + stderr).lower())

    def test_fetch_rejects_invalid_mem_selector(self) -> None:
        code, stdout, stderr = self._run_cli_expect_system_exit(
            ["fetch", "--mem", "GPIOA:"]
        )
        self.assertNotEqual(code, 0)
        self.assertIn("invalid memory selector", (stdout + stderr).lower())

    def test_report_tail_requires_positive_integer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(
                [
                    "report",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--gdb",
                    "--tail",
                    "0",
                ]
            )

        self.assertNotEqual(code, 0)
        self.assertIn("tail", (stdout + stderr).lower())
        self.assertIn("positive", (stdout + stderr).lower())

    def test_report_vars_fails_when_requested_names_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            code, stdout, stderr = self._run_cli_expect_system_exit(
                [
                    "report",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--vars",
                    "definitely_missing",
                ]
            )

        self.assertNotEqual(code, 0)
        self.assertIn("definitely_missing", stdout + stderr)
        self.assertIn("no matches", (stdout + stderr).lower())

    def test_fetch_with_mem_captures_entries_and_prints_memory_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            byte_values = {
                0x20002000: "0x41",
                0x20002001: "0x42",
                0x20002002: "0x43",
                0x00002000: "0xde",
                0x00002001: "0xad",
            }
            try:
                with _FakeOpenOcdServer(values=byte_values) as server:
                    stdout, _ = self._run_cli_in_workspace(
                        workspace,
                        [
                            "fetch",
                            "--mem",
                            "0x20002000:3",
                            "--mem",
                            "8192:2",
                            "--openocd-tcl-host",
                            server.host,
                            "--openocd-tcl-port",
                            str(server.port),
                        ],
                        capture_stderr=True,
                    )
            except PermissionError:
                self.skipTest("sandbox blocks loopback socket creation")
            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertIn("Memory: present", stdout)
        self.assertIn("--mem [ADDR:SIZE ...]", stdout)
        self.assertEqual(payload["provenance"]["memory_read_requested_count"], 2)
        self.assertEqual(payload["provenance"]["memory_read_success_count"], 2)
        self.assertEqual(payload["provenance"]["memory_read_failure_count"], 0)
        entries = payload["sources"]["memory"]["entries"]
        self.assertEqual(
            [entry["address"] for entry in entries], ["8192", "0x20002000"]
        )
        self.assertEqual(entries[0]["data_hex"], "de ad")
        self.assertEqual(entries[1]["data_hex"], "41 42 43")

    def test_fetch_with_mem_all_failures_writes_snapshot_then_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            try:
                with _FakeOpenOcdServer(values={}) as server:
                    code, stdout, stderr = (
                        self._run_cli_expect_system_exit_in_workspace(
                            workspace,
                            [
                                "fetch",
                                "--mem",
                                "0x20002000:3",
                                "--openocd-tcl-host",
                                server.host,
                                "--openocd-tcl-port",
                                str(server.port),
                            ],
                        )
                    )
            except PermissionError:
                self.skipTest("sandbox blocks loopback socket creation")

            payload = json.loads(
                (workspace / "latest_snapshot.json").read_text(encoding="utf-8")
            )

        self.assertNotEqual(code, 0)
        self.assertIn(
            "no memory ranges were captured successfully", (stdout + stderr).lower()
        )
        self.assertEqual(payload["provenance"]["memory_read_requested_count"], 1)
        self.assertEqual(payload["provenance"]["memory_read_success_count"], 0)
        self.assertEqual(payload["provenance"]["memory_read_failure_count"], 1)
        self.assertEqual(
            payload["sources"]["memory"]["entries"][0]["status"], "failure"
        )

    def test_report_mem_outputs_all_entries_sorted_by_address_then_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            payload["sources"]["memory"] = {
                "embedded": True,
                "entries": [
                    {
                        "status": "success",
                        "address": "0x20002000",
                        "size": 3,
                        "data_hex": "41 42 43",
                        "failure_reason": None,
                        "ascii_preview": "ABC",
                    },
                    {
                        "status": "success",
                        "address": "8192",
                        "size": 2,
                        "data_hex": "de ad",
                        "failure_reason": None,
                        "ascii_preview": "..",
                    },
                ],
            }
            snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
            output = self._run_cli(
                ["report", "--snapshot-file", str(snapshot_path), "--mem"]
            )

        rendered = json.loads(output)
        self.assertEqual(
            [entry["address"] for entry in rendered["memory"]["entries"]],
            ["8192", "0x20002000"],
        )
        self.assertEqual(
            rendered["metadata"]["source_availability"]["memory"],
            "present",
        )

    def test_report_mem_selectors_use_normalized_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            payload["sources"]["memory"] = {
                "embedded": True,
                "entries": [
                    {
                        "status": "success",
                        "address": "8192",
                        "size": 2,
                        "data_hex": "de ad",
                        "failure_reason": None,
                        "ascii_preview": "..",
                    }
                ],
            }
            snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
            output = self._run_cli(
                [
                    "report",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--mem",
                    "0x2000:2",
                ]
            )

        rendered = json.loads(output)
        self.assertEqual(len(rendered["memory"]["entries"]), 1)
        self.assertEqual(rendered["memory"]["entries"][0]["address"], "8192")

    def test_report_mem_fails_when_no_matches_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = self._write_snapshot(Path(tmpdir) / "latest_snapshot.json")
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            payload["sources"]["memory"] = {
                "embedded": True,
                "entries": [
                    {
                        "status": "success",
                        "address": "8192",
                        "size": 2,
                        "data_hex": "de ad",
                        "failure_reason": None,
                        "ascii_preview": "..",
                    }
                ],
            }
            snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
            code, stdout, stderr = self._run_cli_expect_system_exit(
                [
                    "report",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--mem",
                    "0x20002000:1",
                ]
            )

        self.assertNotEqual(code, 0)
        self.assertIn(
            "no matches found for requested memory", (stdout + stderr).lower()
        )
        self.assertIn("0x20002000:1", stdout + stderr)

    def test_fetch_discovery_failure_lists_checked_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                stdout, stderr, code = self._run_cli_capture(["fetch"])
            finally:
                os.chdir(previous)

        self.assertEqual(code, 2)
        message = (stdout + stderr).strip()
        self.assertIn("could not auto-resolve an input source", message)
        self.assertIn("cortex-debug-shared-mi.log", message)
        self.assertIn("session.rtt", message)

    def test_fetch_without_valid_input_returns_resolution_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout, stderr, exit_code = self._run_cli_capture(
                ["fetch", "--workspace-root", tmpdir]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("could not auto-resolve an input source", stderr)

    def test_fetch_with_gdb_only_emits_structured_warning_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            stdout, stderr, exit_code = self._run_cli_capture(
                [
                    "fetch",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--workspace-root",
                    tmpdir,
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("DebugOracle Fetch Summary", stdout)
        self.assertIn("No RTT lines were available", stderr)
        self.assertIn(
            "No RTT lines were available for this snapshot.",
            payload["parse_warnings"],
        )

    def test_fetch_with_rtt_only_emits_missing_gdb_warning_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            _, stderr, exit_code = self._run_cli_capture(
                [
                    "fetch",
                    "--rtt",
                    str(FIXTURES / "sample.rtt"),
                    "--workspace-root",
                    tmpdir,
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        warning = "No GDB/MI input was provided before building this snapshot."
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.count(warning), 1)
        self.assertIn(warning, payload["parse_warnings"])

    def test_fetch_bounds_and_redacts_parse_warnings_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            gdb_mi = workspace / "untrusted.mi"
            gdb_mi.write_text(
                "\n".join(
                    f'^done,locals={{value="TOPSECRET-{index}\x1b[31m",'
                    for index in range(12)
                ),
                encoding="utf-8",
            )
            snapshot_path = workspace / "snapshot.json"

            _, stderr, exit_code = self._run_cli_capture(
                [
                    "fetch",
                    "--gdb-mi",
                    str(gdb_mi),
                    "--workspace-root",
                    str(workspace),
                    "--state-out",
                    str(snapshot_path),
                ]
            )
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        warning_lines = [
            line for line in stderr.splitlines() if line.startswith("Warning:")
        ]
        self.assertEqual(exit_code, 0)
        self.assertNotIn("TOPSECRET", stderr)
        self.assertNotIn("\x1b", stderr)
        self.assertIn("details retained in the snapshot", stderr)
        self.assertRegex(stderr, r"\d+ additional warnings omitted")
        self.assertLessEqual(len(warning_lines), 9)
        self.assertTrue(
            any("TOPSECRET" in warning for warning in payload["parse_warnings"])
        )

    def test_fetch_warning_rendering_escapes_controls_and_bounds_length(self) -> None:
        rendered = _warning_for_stderr("\0\x1b\n\t\u202e" + "x" * 1024)

        self.assertLessEqual(len(rendered), 512)
        self.assertNotIn("\0", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\t", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn(r"\x1b", rendered)
        self.assertIn(r"\u202e", rendered)
        self.assertTrue(rendered.endswith("..."))

    def test_fetch_rejects_symlinked_workspace_state_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            sentinel = Path(tmpdir) / "outside.json"
            sentinel.write_text("sentinel", encoding="utf-8")
            state_out = workspace / "snapshot.json"
            state_out.symlink_to(sentinel)

            code, stdout, stderr = self._run_cli_expect_system_exit(
                [
                    "fetch",
                    "--gdb-mi",
                    str(FIXTURES / "sample.mi"),
                    "--workspace-root",
                    str(workspace),
                    "--state-out",
                    str(state_out),
                ]
            )
            sentinel_content = sentinel.read_text(encoding="utf-8")

        self.assertNotEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("safely write", stderr.lower())
        self.assertEqual(sentinel_content, "sentinel")

    def test_capture_rtt_rejects_out_of_range_port_before_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "debugoracle.cli.commands.status_capture.capture_rtt"
            ) as capture:
                code, stdout, stderr = self._run_cli_expect_system_exit(
                    [
                        "capture-rtt",
                        "--port",
                        "70000",
                        "--output",
                        str(Path(tmpdir) / "session.rtt"),
                    ]
                )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("port must be between 1 and 65535", stderr)
        capture.assert_not_called()

    def test_all_tcp_cli_surfaces_reject_out_of_range_ports(self) -> None:
        invalid_commands = [
            ["run", "--port", "0"],
            [
                "fetch",
                "--gdb-mi",
                str(FIXTURES / "sample.mi"),
                "--openocd-tcl-port",
                "65536",
            ],
            ["init-workspace", "--auto", "--rtt-port", "-1"],
        ]

        for argv in invalid_commands:
            with self.subTest(argv=argv):
                code, stdout, stderr = self._run_cli_expect_system_exit(argv)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("port must be between 1 and 65535", stderr)

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
        save_artifact(bundle, str(path))
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

    def _run_cli_capture(
        self,
        argv: list[str],
    ) -> tuple[str, str, int]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return stdout.getvalue(), stderr.getvalue(), exit_code

    def _run_cli_capture_in_workspace(
        self,
        workspace: Path,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, int]:
        previous = os.getcwd()
        try:
            os.chdir(workspace)
            with patch.dict(os.environ, env or {}, clear=False):
                return self._run_cli_capture(argv)
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


class _VirtualOpenOcdSocket:
    def __init__(self, server: "_FakeOpenOcdServer") -> None:
        self._server = server
        self._buffer = bytearray()
        self._closed = False

    def settimeout(self, _: float) -> None:
        return

    def sendall(self, payload: bytes) -> None:
        if self._closed:
            raise OSError("socket is closed")
        chunks = payload.split(b"\x1a")
        for raw_command in chunks:
            if not raw_command:
                continue
            command = raw_command.decode("utf-8", errors="replace").strip()
            response = self._server.build_response(command)
            self._buffer.extend(response.encode("utf-8") + b"\x1a")

    def recv(self, size: int) -> bytes:
        if self._closed:
            return b""
        if not self._buffer:
            return b""
        take = min(size, len(self._buffer))
        chunk = bytes(self._buffer[:take])
        del self._buffer[:take]
        return chunk

    def close(self) -> None:
        self._closed = True


class _FakeOpenOcdServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, *, values: dict[int, str]) -> None:
        self._values = values
        self._init_error: PermissionError | None = None
        self._virtual_mode = False
        self._create_connection_patcher = None
        try:
            super().__init__(("127.0.0.1", 0), _FakeOpenOcdHandler)
        except PermissionError as error:
            self._init_error = error
            self._virtual_mode = True
            self._thread = None
            self.server_address = ("127.0.0.1", 65535)
            return
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        return str(self.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def __enter__(self) -> "_FakeOpenOcdServer":
        if self._virtual_mode:
            self._create_connection_patcher = patch(
                "socket.create_connection",
                side_effect=self._create_virtual_connection,
            )
            self._create_connection_patcher.start()
            return self
        assert self._thread is not None
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._virtual_mode:
            if self._create_connection_patcher is not None:
                self._create_connection_patcher.stop()
            return
        assert self._thread is not None
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

    def _create_virtual_connection(self, *args, **_kwargs) -> _VirtualOpenOcdSocket:
        endpoint = args[0] if args else None
        if not isinstance(endpoint, tuple) or len(endpoint) < 2:
            raise OSError("Connection refused")
        host = str(endpoint[0])
        port = int(endpoint[1])
        allowed_hosts = {self.host, "127.0.0.1", "localhost"}
        if host not in allowed_hosts or port != self.port:
            raise OSError("Connection refused")
        return _VirtualOpenOcdSocket(self)


if __name__ == "__main__":
    unittest.main()
