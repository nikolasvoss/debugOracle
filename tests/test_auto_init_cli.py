from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from debugoracle.cli import main
from debugoracle.docs_sidecar import search_documents
from debugoracle.readiness import collect_workspace_plan


class AutomaticWorkspaceInitCliTests(unittest.TestCase):
    def test_missing_consent_inventories_docs_without_parsing_or_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            docs_dir = workspace / "docs" / "vendor"
            docs_dir.mkdir(parents=True)
            source = docs_dir / "reference.pdf"
            source.write_bytes(b"untrusted bytes that must not be parsed")

            with patch(
                "debugoracle.cli.commands.init_workspace.ingest_documents",
                side_effect=AssertionError("PDF parser boundary was crossed"),
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["schema_version"], "1")
            self.assertEqual(payload["scope"], "automatic_workspace_init")
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(
                [item["name"] for item in payload["capabilities"]],
                ["documentation", "debug_scaffold", "register_catalog"],
            )
            documentation = payload["capabilities"][0]
            self.assertEqual(documentation["status"], "partial")
            self.assertEqual(
                documentation["inputs"],
                [
                    {
                        "key": "documents",
                        "values": [str(source.resolve())],
                        "provenance": "workspace_discovery",
                    }
                ],
            )
            self.assertEqual(
                documentation["actions"][0]["action_id"],
                "authorize_document_ingest",
            )
            self.assertFalse(documentation["application"]["attempted"])
            self.assertFalse(Path(f"{source}.dbgoracle-docs").exists())

    def test_docs_only_authorized_init_indexes_a_real_pdf_without_toolchain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            docs_dir = workspace / "docs" / "vendor"
            docs_dir.mkdir(parents=True)
            source = docs_dir / "reference.pdf"
            self._write_text_pdf(
                source,
                "RCC CCIPR USART1SEL selects the peripheral clock source.",
            )

            stdout, stderr, exit_code = self._run_cli(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--auto",
                    "--yes",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            documentation = payload["capabilities"][0]
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(documentation["status"], "complete")
            self.assertTrue(documentation["application"]["attempted"])
            self.assertEqual(
                documentation["application"]["results"][0]["ingest_state"],
                "clean",
            )
            self.assertFalse((workspace / ".vscode").exists())
            hits = search_documents(
                workspace_root=workspace,
                query="USART1SEL peripheral clock",
            ).hits
            self.assertEqual(len(hits), 1)
            self.assertIn("CCIPR", hits[0].text)

    def test_missing_docs_consent_does_not_block_independent_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            build_dir = workspace / "build"
            build_dir.mkdir()
            (build_dir / "app.elf").write_bytes(b"ELF")
            config_dir = workspace / "config"
            config_dir.mkdir()
            config = config_dir / "target.cfg"
            config.write_text("# target\n", encoding="utf-8")
            docs_dir = workspace / "docs"
            docs_dir.mkdir()
            source = docs_dir / "reference.pdf"
            source.write_bytes(b"must remain unparsed")

            with (
                patch(
                    "debugoracle.cli.commands.init_workspace.ingest_documents",
                    side_effect=AssertionError("PDF parser boundary was crossed"),
                ),
                patch(
                    "debugoracle.cli.commands.init_workspace.shutil.which",
                    return_value="/usr/bin/openocd",
                ),
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--openocd-config",
                        str(config),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(
                [item["status"] for item in payload["capabilities"][:2]],
                ["partial", "complete"],
            )
            self.assertTrue((workspace / ".vscode" / "launch.json").is_file())
            self.assertFalse(Path(f"{source}.dbgoracle-docs").exists())

    def test_full_unambiguous_auto_init_applies_all_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "build").mkdir()
            (workspace / "build" / "app.elf").write_bytes(b"ELF fixture")
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            svd = session_dir / "device.svd"
            svd.write_text("<device/>", encoding="utf-8")
            config_dir = workspace / "config"
            config_dir.mkdir()
            interface = config_dir / "interface.cfg"
            target = config_dir / "target.cfg"
            interface.write_text("# interface\n", encoding="utf-8")
            target.write_text("# target\n", encoding="utf-8")
            docs_dir = workspace / "docs" / "vendor"
            docs_dir.mkdir(parents=True)
            self._write_text_pdf(docs_dir / "reference.pdf", "USART register catalog")

            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--yes",
                        "--openocd-config",
                        "config/interface.cfg",
                        "--openocd-config",
                        "config/target.cfg",
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(
                [item["status"] for item in payload["capabilities"]],
                ["complete", "complete", "complete"],
            )
            settings = json.loads(
                (workspace / ".vscode" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                settings["debugoracle.executable"],
                str((workspace / "build" / "app.elf").resolve()),
            )
            self.assertEqual(settings["debugoracle.svdFile"], str(svd.resolve()))
            self.assertEqual(
                settings["debugoracle.openocdConfigFiles"],
                [str(interface.resolve()), str(target.resolve())],
            )

    def test_auto_init_never_overwrites_user_owned_vscode_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            build_dir = workspace / "build"
            build_dir.mkdir()
            executable = build_dir / "app.elf"
            executable.write_bytes(b"ELF")
            config_dir = workspace / "config"
            config_dir.mkdir()
            config = config_dir / "target.cfg"
            config.write_text("# target\n", encoding="utf-8")
            vscode_dir = workspace / ".vscode"
            vscode_dir.mkdir()
            original = {
                vscode_dir / "settings.json": b'{"editor.tabSize": 2}\n',
                vscode_dir
                / "launch.json": b'{"version":"0.2.0","configurations":[]}\n',
                vscode_dir / "tasks.json": b'{"version":"2.0.0","tasks":[]}\n',
            }
            for path, content in original.items():
                path.write_bytes(content)

            stdout, stderr, exit_code = self._run_cli(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--auto",
                    "--executable",
                    str(executable),
                    "--openocd-config",
                    str(config),
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["capabilities"][1]["status"], "partial")
            self.assertEqual(
                payload["capabilities"][1]["application"]["blocked_files"],
                sorted(str(path) for path in original),
            )
            for path, content in original.items():
                self.assertEqual(path.read_bytes(), content)

    def test_auto_init_persists_an_explicit_svd_without_debug_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            board_dir = workspace / "boards"
            board_dir.mkdir()
            svd = board_dir / "device.svd"
            svd.write_text("<device/>", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--auto",
                    "--svd-file",
                    "boards/device.svd",
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            settings_path = workspace / ".vscode" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["capabilities"][2]["status"], "complete")
            self.assertEqual(settings["debugoracle.svdFile"], str(svd.resolve()))
            self.assertEqual(
                settings["debugoracle.managedBy"], "dbgoracle init-workspace"
            )
            self.assertFalse((workspace / ".vscode" / "launch.json").exists())

    def test_auto_attach_never_persists_an_explicit_svd_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            board_dir = workspace / "boards"
            board_dir.mkdir()
            svd = board_dir / "device.svd"
            svd.write_text("<device/>", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--auto",
                    "--attach",
                    "--force",
                    "--svd-file",
                    str(svd),
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            register = payload["capabilities"][2]
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(register["status"], "partial")
            self.assertEqual(register["application"]["state"], "blocked")
            self.assertFalse((workspace / ".vscode").exists())

    def test_auto_init_does_not_write_through_symlinked_output_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)
            workspace = sandbox / "workspace"
            outside_vscode = sandbox / "outside-vscode"
            outside_session = sandbox / "outside-session"
            for directory in (workspace, outside_vscode, outside_session):
                directory.mkdir()
            (workspace / "build").mkdir()
            executable = workspace / "build" / "app.elf"
            executable.write_bytes(b"ELF")
            (workspace / "config").mkdir()
            config = workspace / "config" / "target.cfg"
            config.write_text("# target\n", encoding="utf-8")
            (workspace / "boards").mkdir()
            svd = workspace / "boards" / "device.svd"
            svd.write_text("<device/>", encoding="utf-8")
            (workspace / ".vscode").symlink_to(outside_vscode, target_is_directory=True)
            (workspace / ".dbgoracle").symlink_to(
                outside_session, target_is_directory=True
            )

            stdout, stderr, exit_code = self._run_cli(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--auto",
                    "--executable",
                    str(executable),
                    "--openocd-config",
                    str(config),
                    "--svd-file",
                    str(svd),
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(
                [item["status"] for item in payload["capabilities"]],
                ["unavailable", "partial", "partial"],
            )
            self.assertEqual(list(outside_vscode.iterdir()), [])
            self.assertEqual(list(outside_session.iterdir()), [])

    def test_unchanged_auto_init_rerun_is_content_and_result_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "build").mkdir()
            (workspace / "build" / "app.elf").write_bytes(b"ELF")
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "device.svd").write_text("<device/>", encoding="utf-8")
            config_dir = workspace / "config"
            config_dir.mkdir()
            config = config_dir / "target.cfg"
            config.write_text("# target\n", encoding="utf-8")
            docs_dir = workspace / "docs"
            docs_dir.mkdir()
            source = docs_dir / "reference.pdf"
            self._write_text_pdf(source, "RCC clock selection")
            argv = [
                "init-workspace",
                "--workspace-root",
                str(workspace),
                "--auto",
                "--yes",
                "--openocd-config",
                str(config),
                "--format",
                "json",
            ]

            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                first_stdout, first_stderr, first_exit = self._run_cli(argv)
                tracked = tuple(
                    sorted(
                        path
                        for directory in (
                            workspace / ".vscode",
                            Path(f"{source}.dbgoracle-docs"),
                        )
                        for path in directory.rglob("*")
                        if path.is_file()
                    )
                )
                before = {
                    path: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in tracked
                }
                second_stdout, second_stderr, second_exit = self._run_cli(argv)

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            self.assertEqual(first_stderr, "")
            self.assertEqual(second_stderr, "")
            self.assertEqual(json.loads(first_stdout), json.loads(second_stdout))
            self.assertEqual(
                before,
                {
                    path: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in tracked
                },
            )

    def test_document_failure_does_not_suppress_scaffold_or_register_setup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "build").mkdir()
            (workspace / "build" / "app.elf").write_bytes(b"ELF")
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "device.svd").write_text("<device/>", encoding="utf-8")
            config_dir = workspace / "config"
            config_dir.mkdir()
            config = config_dir / "target.cfg"
            config.write_text("# target\n", encoding="utf-8")
            docs_dir = workspace / "docs"
            docs_dir.mkdir()
            (docs_dir / "broken.pdf").write_bytes(b"not a PDF")

            with patch(
                "debugoracle.cli.commands.init_workspace.shutil.which",
                return_value="/usr/bin/openocd",
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--yes",
                        "--openocd-config",
                        str(config),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(
                [item["status"] for item in payload["capabilities"]],
                ["partial", "complete", "complete"],
            )
            self.assertEqual(
                payload["capabilities"][0]["application"]["results"][0]["ingest_state"],
                "failed",
            )
            self.assertTrue((workspace / ".vscode" / "launch.json").is_file())

    def test_document_application_exception_does_not_suppress_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "build").mkdir()
            executable = workspace / "build" / "app.elf"
            executable.write_bytes(b"ELF")
            (workspace / "config").mkdir()
            config = workspace / "config" / "target.cfg"
            config.write_text("# target\n", encoding="utf-8")
            (workspace / "docs").mkdir()
            (workspace / "docs" / "reference.pdf").write_bytes(b"fixture")

            with (
                patch(
                    "debugoracle.cli.commands.init_workspace.ingest_documents",
                    side_effect=OSError("sidecar storage unavailable"),
                ),
                patch(
                    "debugoracle.cli.commands.init_workspace.shutil.which",
                    return_value="/usr/bin/openocd",
                ),
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--yes",
                        "--executable",
                        str(executable),
                        "--openocd-config",
                        str(config),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            documentation, scaffold, _register = payload["capabilities"]
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(documentation["status"], "partial")
            self.assertIn("storage unavailable", documentation["application"]["error"])
            self.assertEqual(scaffold["status"], "complete")
            self.assertTrue((workspace / ".vscode" / "launch.json").is_file())

    def test_register_write_failure_is_reported_without_unstructured_abort(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "boards").mkdir()
            svd = workspace / "boards" / "device.svd"
            svd.write_text("<device/>", encoding="utf-8")

            with patch(
                "pathlib.Path.write_text",
                side_effect=OSError("settings storage unavailable"),
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--svd-file",
                        str(svd),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            register = payload["capabilities"][2]
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(register["status"], "partial")
            self.assertEqual(register["application"]["state"], "failed")
            self.assertIn("storage unavailable", register["application"]["error"])

    def test_post_application_inventory_failure_preserves_capability_results(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            session_dir = workspace / ".dbgoracle"
            session_dir.mkdir()
            svd = session_dir / "device.svd"
            svd.write_text("<device/>", encoding="utf-8")
            initial_plan = collect_workspace_plan(workspace)

            with patch(
                "debugoracle.cli.commands.init_workspace.collect_workspace_plan",
                side_effect=[initial_plan, OSError("inventory unavailable")],
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(len(payload["capabilities"]), 3)
            self.assertEqual(payload["capabilities"][2]["status"], "complete")
            self.assertIn("re-inventory failed", payload["error"])

    def test_auto_init_rejects_explicit_files_outside_the_workspace(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            tempfile.TemporaryDirectory() as outside_dir,
        ):
            workspace = Path(tmpdir)
            outside = Path(outside_dir) / "target.cfg"
            outside.write_text("# target\n", encoding="utf-8")

            stdout, stderr, exit_code = self._run_cli(
                [
                    "init-workspace",
                    "--workspace-root",
                    str(workspace),
                    "--auto",
                    "--openocd-config",
                    str(outside),
                    "--format",
                    "json",
                ]
            )

            payload = json.loads(stdout)
            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(payload["status"], "failed")
            self.assertIn("outside the workspace", payload["error"])
            self.assertFalse((workspace / ".vscode").exists())
            self.assertFalse((workspace / ".dbgoracle").exists())

    def test_auto_init_performs_no_subprocess_or_socket_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with (
                patch(
                    "subprocess.run",
                    side_effect=AssertionError("subprocess execution is forbidden"),
                ),
                patch(
                    "socket.socket",
                    side_effect=AssertionError("socket access is forbidden"),
                ),
            ):
                stdout, stderr, exit_code = self._run_cli(
                    [
                        "init-workspace",
                        "--workspace-root",
                        str(workspace),
                        "--auto",
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(json.loads(stdout)["status"], "failed")

    def test_auto_init_text_output_exposes_provenance_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            docs_dir = workspace / "docs"
            docs_dir.mkdir()
            source = docs_dir / "reference.pdf"
            source.write_bytes(b"inventory only")

            stdout, stderr, exit_code = self._run_cli(
                ["init-workspace", "--workspace-root", str(workspace), "--auto"]
            )

            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertIn("documentation: partial", stdout)
            self.assertIn("documents (workspace_discovery)", stdout)
            self.assertIn(str(source.resolve()), stdout)
            self.assertIn("authorize local PDF parsing", stdout)

    @staticmethod
    def _write_text_pdf(path: Path, text: str) -> None:
        writer = PdfWriter()
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        font_ref = writer._add_object(font)
        page = writer.add_blank_page(width=500, height=200)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 20 100 Td ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        with path.open("wb") as output:
            writer.write(output)

    @staticmethod
    def _run_cli(argv: list[str]) -> tuple[str, str, int]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return stdout.getvalue(), stderr.getvalue(), exit_code


if __name__ == "__main__":
    unittest.main()
