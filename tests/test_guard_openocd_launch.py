from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from debugoracle.cli.main import main
from debugoracle.openocd import OpenOcdProcess


class GuardOpenOcdLaunchTests(unittest.TestCase):
    def _write_attach_workspace(self, workspace: Path) -> None:
        vscode_dir = workspace / ".vscode"
        vscode_dir.mkdir(parents=True)
        (vscode_dir / "settings.json").write_text(
            json.dumps(
                {
                    "debugoracle.workspaceSetupMode": "attach",
                    "debugoracle.launchConfigName": "DebugOracle: Attach STM32",
                    "debugoracle.launchConfigRole": "golden-path-attach",
                }
            ),
            encoding="utf-8",
        )
        (vscode_dir / "launch.json").write_text(
            json.dumps(
                {
                    "version": "0.2.0",
                    "configurations": [
                        {
                            "name": "DebugOracle: Attach STM32",
                            "debugoracleRole": "golden-path-attach",
                            "preLaunchTask": "DebugOracle: Prelaunch",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (vscode_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "version": "2.0.0",
                    "tasks": [
                        {
                            "label": "DebugOracle: Prelaunch",
                            "dependsOn": ["Prepare debug logs"],
                        },
                        {
                            "label": "Prepare debug logs",
                            "type": "shell",
                            "command": "mkdir -p .dbgoracle",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_guard_openocd_launch_fails_early_when_workspace_setup_is_incomplete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    ["guard-openocd-launch", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("workspace setup is not finished", stderr.getvalue())
        self.assertIn("Run `dbgoracle init-workspace --attach", stderr.getvalue())

    def test_guard_openocd_launch_fails_early_when_workspace_setup_is_degraded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_attach_workspace(workspace)
            (workspace / ".vscode" / "tasks.json").write_text(
                json.dumps(
                    {
                        "version": "2.0.0",
                        "tasks": [
                            {
                                "label": "Prepare debug logs",
                                "type": "shell",
                                "command": "mkdir -p .dbgoracle",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.guard_openocd_launch.discover_openocd_processes",
                ) as discover_mock,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["guard-openocd-launch", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("workspace setup is not finished", stderr.getvalue())
        self.assertIn("task is missing", stderr.getvalue())
        discover_mock.assert_not_called()

    def test_guard_openocd_launch_passes_when_no_matching_process_exists(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            tempfile.TemporaryDirectory() as otherdir,
        ):
            workspace = Path(tmpdir)
            self._write_attach_workspace(workspace)
            process = OpenOcdProcess(
                pid=1111,
                argv=("openocd", "-f", "interface/stlink.cfg"),
                cwd=otherdir,
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.guard_openocd_launch.discover_openocd_processes",
                    return_value=[process],
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["guard-openocd-launch", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "no conflicting workspace-matching OpenOCD session", stdout.getvalue()
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_guard_openocd_launch_blocks_matching_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_attach_workspace(workspace)
            process = OpenOcdProcess(
                pid=2222,
                argv=("openocd", "-f", "interface/stlink.cfg"),
                cwd=str(workspace),
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.guard_openocd_launch.discover_openocd_processes",
                    return_value=[process],
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["guard-openocd-launch", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("`make debug` is still active", stderr.getvalue())

    def test_guard_openocd_launch_fails_clearly_for_ambiguous_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_attach_workspace(workspace)
            processes = [
                OpenOcdProcess(
                    pid=3333,
                    argv=("openocd", "-s", str(workspace)),
                    cwd=str(workspace),
                ),
                OpenOcdProcess(
                    pid=4444,
                    argv=("openocd", "-s", str(workspace)),
                    cwd=str(workspace),
                ),
            ]

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.guard_openocd_launch.discover_openocd_processes",
                    return_value=processes,
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["guard-openocd-launch", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("multiple workspace-matching OpenOCD sessions", stderr.getvalue())

    def test_guard_openocd_launch_blocks_when_process_discovery_lacks_workspace_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_attach_workspace(workspace)
            process = OpenOcdProcess(
                pid=5555,
                argv=("openocd", "-f", "interface/stlink.cfg"),
                cwd=None,
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "debugoracle.cli.commands.guard_openocd_launch.discover_openocd_processes",
                    return_value=[process],
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    ["guard-openocd-launch", "--workspace-root", str(workspace)]
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(
            "could not safely determine workspace ownership", stderr.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
