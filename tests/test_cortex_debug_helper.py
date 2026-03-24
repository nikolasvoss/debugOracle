import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from debugoracle.cli.commands import find_tcl_port as helper


class FindTclPortHelperTests(unittest.TestCase):
    def test_discover_openocd_candidates_falls_back_to_ps_when_proc_has_no_matches(self) -> None:
        ps_text = " 1234 openocd -c \"gdb_port 50000\" -c \"tcl_port 50001\" -c \"telnet_port 50002\"\n"
        with patch(
            "debugoracle.openocd._discover_openocd_candidates_from_proc",
            return_value=[],
        ), patch(
            "debugoracle.openocd._discover_openocd_candidates_from_ps",
            return_value=list(helper.parse_ps_output(ps_text)),
        ):
            candidates = list(helper.discover_openocd_candidates())

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].tcl_port, 50001)

    def test_select_candidate_returns_none_for_ambiguous_unmatched_sessions(self) -> None:
        workspace_root = Path("/tmp/current-workspace")
        candidates = [
            helper.OpenOcdCandidate(
                pid=100,
                argv=("openocd", "-c", "tcl_port 40001"),
                cwd=None,
                host="127.0.0.1",
                tcl_port=40001,
                gdb_port=None,
                telnet_port=None,
            ),
            helper.OpenOcdCandidate(
                pid=200,
                argv=("openocd", "-c", "tcl_port 50001"),
                cwd=None,
                host="127.0.0.1",
                tcl_port=50001,
                gdb_port=None,
                telnet_port=None,
            ),
        ]

        selected = helper.select_candidate(
            candidates,
            workspace_root=workspace_root,
            requested_pid=None,
        )

        self.assertIsNone(selected)
    def test_parse_openocd_ports_from_command_arguments(self) -> None:
        ports = helper.parse_openocd_ports(
            (
                "openocd",
                "-c",
                "gdb_port 50000",
                "-c",
                "tcl_port 50001",
                "-c",
                "telnet_port 50002",
            )
        )

        self.assertEqual(
            ports,
            {
                "gdb_port": 50000,
                "tcl_port": 50001,
                "telnet_port": 50002,
            },
        )

    def test_select_candidate_prefers_workspace_cwd(self) -> None:
        workspace_root = Path("/tmp/current-workspace")
        other = helper.OpenOcdCandidate(
            pid=100,
            argv=("openocd", "-c", "tcl_port 40001"),
            cwd="/tmp/other-workspace",
            host="127.0.0.1",
            tcl_port=40001,
            gdb_port=None,
            telnet_port=None,
        )
        current = helper.OpenOcdCandidate(
            pid=200,
            argv=("openocd", "-c", "tcl_port 50001"),
            cwd=str(workspace_root),
            host="127.0.0.1",
            tcl_port=50001,
            gdb_port=None,
            telnet_port=None,
        )

        selected = helper.select_candidate(
            [other, current],
            workspace_root=workspace_root,
            requested_pid=None,
        )

        self.assertEqual(selected, current)

    def test_resolve_svd_file_prefers_workspace_default_setting_with_jsonc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            (workspace_root / ".vscode").mkdir()
            (workspace_root / ".vscode" / "settings.json").write_text(
                """
                {
                  // project default
                  "debugoracle.svdFile": "${workspaceFolder}/.dbgoracle/board.svd",
                }
                """,
                encoding="utf-8",
            )
            (workspace_root / ".dbgoracle").mkdir()
            (workspace_root / ".dbgoracle" / "board.svd").write_text("<device />\n", encoding="utf-8")

            resolved, notice = helper.resolve_svd_file(workspace_root)

        self.assertEqual(resolved, str(workspace_root / ".dbgoracle" / "board.svd"))
        self.assertIn("Workspace default SVD for fetch:", notice)

    def test_build_fetch_command_includes_explicit_tcl_port(self) -> None:
        command = helper.build_fetch_command(
            workspace_root=Path("/workspace/project"),
            host="127.0.0.1",
            tcl_port=50001,
            svd_file="/workspace/project/.dbgoracle/device.svd",
        )

        self.assertEqual(
            command,
            "dbgoracle fetch --workspace-root /workspace/project --svd-file "
            "/workspace/project/.dbgoracle/device.svd --openocd-tcl-port 50001",
        )


if __name__ == "__main__":
    unittest.main()
