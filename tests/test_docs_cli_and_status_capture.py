from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from debugoracle.cli.commands import docs_cli, status_capture
from debugoracle.diagnostics import DiagnosticCheck
from debugoracle.docs_sidecar import (
    DocsIngestBatch,
    DocsIngestResult,
    DocsSearchHit,
    DocsSearchResult,
    DocsStatusEntry,
)


def _ingest_result(
    *,
    state: str = "ok",
    parser: str = "pypdf",
    warning_summary: str = "",
    skipped: bool = False,
) -> DocsIngestResult:
    return DocsIngestResult(
        source_pdf="/tmp/doc.pdf",
        sidecar_dir="/tmp/.docs/doc",
        parser_used=parser,
        page_count=3,
        chunk_count=5,
        ingest_state=state,
        warning_summary=warning_summary,
        skipped=skipped,
    )


class DocsCliTests(unittest.TestCase):
    def test_ingest_exit_code_branches(self) -> None:
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(
                    results=[], discovered_candidates=[], confirmation_required=True
                )
            ),
            2,
        )
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(
                    results=[],
                    discovered_candidates=[],
                    invalid_inputs=["missing file"],
                )
            ),
            1,
        )
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(
                    results=[_ingest_result(state="ok")],
                    discovered_candidates=[],
                    invalid_inputs=["x"],
                )
            ),
            2,
        )
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(results=[], discovered_candidates=[])
            ),
            1,
        )
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(
                    results=[_ingest_result(state="failed")], discovered_candidates=[]
                )
            ),
            1,
        )
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(
                    results=[_ingest_result(state="partial")], discovered_candidates=[]
                )
            ),
            2,
        )
        self.assertEqual(
            docs_cli._ingest_exit_code(
                DocsIngestBatch(
                    results=[_ingest_result(state="ok")], discovered_candidates=[]
                )
            ),
            0,
        )

    def test_make_progress_cb_and_next_steps_lines(self) -> None:
        self.assertIsNone(docs_cli._make_progress_cb(enabled=False))
        progress = docs_cli._make_progress_cb(enabled=True)
        self.assertIsNotNone(progress)
        out = io.StringIO()
        with redirect_stdout(out):
            progress(1, 1, "parse")
        self.assertIn("parse: 1/1 pages", out.getvalue())

        with patch.object(docs_cli, "_docling_installed", return_value=True):
            lines = docs_cli._next_steps_lines(
                [_ingest_result(state="partial"), _ingest_result(state="failed")]
            )
        self.assertIn("Next:", lines[0])
        self.assertTrue(any("--parser docling --force" in line for line in lines))
        self.assertTrue(any("docs doctor" in line for line in lines))

    def test_render_ingest_text_and_json(self) -> None:
        batch = DocsIngestBatch(
            results=[
                _ingest_result(
                    state="warning",
                    parser="pypdf",
                    warning_summary="warn",
                    skipped=True,
                )
            ],
            discovered_candidates=["/tmp/docs/a.pdf"],
            warnings=["top-level warning"],
            confirmation_required=True,
        )
        with patch(
            "debugoracle.cli.commands.docs_cli._docling_installed", return_value=False
        ):
            text = docs_cli._render_ingest(batch, fmt="text")
        self.assertIn("Discovered candidates:", text)
        self.assertIn("Action: re-run with --yes", text)
        self.assertIn("skipped=unchanged", text)
        self.assertIn("hint: extraction quality may improve with Docling", text)
        self.assertIn("Warnings:", text)
        self.assertIn("Next:", text)

        json_output = docs_cli._render_ingest(batch, fmt="json")
        payload = json.loads(json_output)
        self.assertEqual(payload["results"][0]["ingest_state"], "warning")

    def test_render_search_and_status(self) -> None:
        no_hits = docs_cli._render_search(
            DocsSearchResult(
                query="timer", hits=[], warnings=["index missing"], search_mode="bm25"
            ),
            fmt="text",
        )
        self.assertIn("No results.", no_hits)
        self.assertIn("Warnings:", no_hits)
        self.assertIn("mode=bm25", no_hits)

        hit = DocsSearchHit(
            source_pdf="/tmp/doc.pdf",
            page_start=1,
            page_end=2,
            score=0.87,
            ingest_state="ok",
            warning_summary="",
            text="line1\nline2",
            heading_path="Peripheral > RCC",
        )
        search_text = docs_cli._render_search(
            DocsSearchResult(
                query="rcc", hits=[hit], warnings=[], search_mode="hybrid"
            ),
            fmt="text",
        )
        self.assertIn("heading: Peripheral > RCC", search_text)
        self.assertIn("line1 line2", search_text)
        self.assertIn("mode=hybrid", search_text)

        json_search = docs_cli._render_search(
            DocsSearchResult(
                query="rcc", hits=[hit], warnings=[], search_mode="hybrid"
            ),
            fmt="json",
        )
        self.assertIn('"results"', json_search)
        self.assertIn('"mode"', json_search)

        empty_status = docs_cli._render_status([], fmt="text")
        self.assertIn("No ingested documents found.", empty_status)

        status_item = DocsStatusEntry(
            source_pdf="/tmp/doc.pdf",
            sidecar_dir="/tmp/.docs/doc",
            envelope_path="/tmp/.docs/doc/envelope.json",
            ingest_state="failed",
            parser_used="pypdf",
            page_count=1,
            chunk_count=1,
            warning_summary="bad parse",
            warnings=[],
        )
        status_text = docs_cli._render_status([status_item], fmt="text")
        self.assertIn("state=failed", status_text)
        self.assertIn("warnings: bad parse", status_text)
        self.assertIn('"documents"', docs_cli._render_status([status_item], fmt="json"))

    def test_run_docs_ingest_retries_only_on_yes_answer(self) -> None:
        args = SimpleNamespace(
            workspace_root="/tmp/ws",
            file=[],
            folder=[],
            yes=False,
            parser="pypdf",
            semantic=False,
            force=False,
            no_interactive=False,
            format="text",
            output=None,
        )
        first = DocsIngestBatch(
            results=[],
            discovered_candidates=["/tmp/docs/a.pdf"],
            confirmation_required=True,
        )
        second = DocsIngestBatch(
            results=[_ingest_result(state="ok")],
            discovered_candidates=["/tmp/docs/a.pdf"],
        )

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdin.isatty", return_value=True
            ),
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdout.isatty", return_value=True
            ),
            patch(
                "debugoracle.cli.commands.docs_cli.ingest_documents",
                side_effect=[first, second],
            ) as ingest_mock,
            patch("builtins.input", return_value="yes"),
        ):
            batch = docs_cli._run_docs_ingest(args, progress_cb=None)
        self.assertEqual(len(batch.results), 1)
        self.assertEqual(ingest_mock.call_count, 2)
        self.assertTrue(ingest_mock.call_args.kwargs["confirm_discovered"])

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdin.isatty", return_value=True
            ),
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdout.isatty", return_value=True
            ),
            patch(
                "debugoracle.cli.commands.docs_cli.ingest_documents",
                return_value=first,
            ) as ingest_mock,
            patch("builtins.input", return_value="n"),
        ):
            batch = docs_cli._run_docs_ingest(args, progress_cb=None)
        self.assertEqual(batch, first)
        self.assertEqual(ingest_mock.call_count, 1)

    def test_interactive_enabled_switches(self) -> None:
        args = SimpleNamespace(no_interactive=True, format="text", output=None)
        self.assertFalse(docs_cli._interactive_enabled(args))

        args = SimpleNamespace(no_interactive=False, format="json", output=None)
        with (
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdin.isatty", return_value=True
            ),
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdout.isatty", return_value=True
            ),
        ):
            self.assertFalse(docs_cli._interactive_enabled(args))

        args = SimpleNamespace(no_interactive=False, format="text", output=None)
        with (
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdin.isatty", return_value=True
            ),
            patch(
                "debugoracle.cli.commands.docs_cli.sys.stdout.isatty", return_value=True
            ),
        ):
            self.assertTrue(docs_cli._interactive_enabled(args))

    def test_command_entrypoints_docs_search_status_ingest_and_doctor(self) -> None:
        common_args = dict(format="text", output=None, workspace_root="/tmp/ws")

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.search_documents",
                return_value=DocsSearchResult(query="q", hits=[], warnings=[]),
            ),
            patch("debugoracle.cli.commands.docs_cli.emit") as emit_mock,
        ):
            code = docs_cli.cmd_docs_search(
                SimpleNamespace(**common_args, query="q", limit=5, file=[])
            )
        self.assertEqual(code, 1)
        emit_mock.assert_called_once()

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.search_documents",
                return_value=DocsSearchResult(query="q", hits=[], warnings=["warn"]),
            ),
            patch("debugoracle.cli.commands.docs_cli.emit"),
        ):
            code = docs_cli.cmd_docs_search(
                SimpleNamespace(**common_args, query="q", limit=5, file=[])
            )
        self.assertEqual(code, 2)

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.search_documents",
                return_value=DocsSearchResult(
                    query="q",
                    hits=[
                        DocsSearchHit(
                            source_pdf="/tmp/doc.pdf",
                            page_start=1,
                            page_end=1,
                            score=1.0,
                            ingest_state="ok",
                            warning_summary="",
                            text="abc",
                        )
                    ],
                ),
            ),
            patch("debugoracle.cli.commands.docs_cli.emit"),
        ):
            code = docs_cli.cmd_docs_search(
                SimpleNamespace(**common_args, query="q", limit=5, file=[])
            )
        self.assertEqual(code, 0)

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.status_documents", return_value=[]
            ),
            patch("debugoracle.cli.commands.docs_cli.emit"),
        ):
            code = docs_cli.cmd_docs_status(SimpleNamespace(**common_args, file=[]))
        self.assertEqual(code, 1)

        with (
            patch(
                "debugoracle.cli.commands.docs_cli.status_documents",
                return_value=[
                    DocsStatusEntry(
                        source_pdf="/tmp/doc.pdf",
                        sidecar_dir="/tmp/.docs/doc",
                        envelope_path="/tmp/.docs/doc/envelope.json",
                        ingest_state="failed",
                        parser_used="pypdf",
                        page_count=1,
                        chunk_count=1,
                        warning_summary="warn",
                    )
                ],
            ),
            patch("debugoracle.cli.commands.docs_cli.emit"),
        ):
            code = docs_cli.cmd_docs_status(SimpleNamespace(**common_args, file=[]))
        self.assertEqual(code, 1)

        with (
            patch(
                "debugoracle.cli.commands.docs_cli._run_docs_ingest",
                return_value=DocsIngestBatch(
                    results=[_ingest_result(state="ok")], discovered_candidates=[]
                ),
            ),
            patch("debugoracle.cli.commands.docs_cli.emit") as emit_mock,
        ):
            code = docs_cli.cmd_docs_ingest(
                SimpleNamespace(
                    **common_args,
                    file=[],
                    folder=[],
                    yes=False,
                    parser="pypdf",
                    semantic=False,
                    force=False,
                    no_interactive=True,
                )
            )
        self.assertEqual(code, 0)
        emit_mock.assert_called_once()

        checks_blocked = [
            DiagnosticCheck(
                key="pypdf",
                required=True,
                ready=False,
                detail="missing",
                remedy="pip install pypdf",
            )
        ]
        with (
            patch(
                "debugoracle.cli.commands.docs_cli.collect_docs_doctor_checks",
                return_value=checks_blocked,
            ),
            patch("debugoracle.cli.commands.docs_cli.emit") as emit_mock,
        ):
            code = docs_cli.cmd_docs_doctor(SimpleNamespace(format="json", output=None))
        self.assertEqual(code, 1)
        self.assertIn('"required_ready": false', emit_mock.call_args.args[0])

        checks_optional = [
            DiagnosticCheck(
                key="docling",
                required=False,
                ready=False,
                detail="missing",
                remedy="install docling",
            )
        ]
        with (
            patch(
                "debugoracle.cli.commands.docs_cli.collect_docs_doctor_checks",
                return_value=checks_optional,
            ),
            patch("debugoracle.cli.commands.docs_cli.emit") as emit_mock,
        ):
            code = docs_cli.cmd_docs_doctor(SimpleNamespace(format="text", output=None))
        self.assertEqual(code, 2)
        self.assertIn("Status: ready for default ingest", emit_mock.call_args.args[0])

        checks_ready = [
            DiagnosticCheck(
                key="pypdf",
                required=True,
                ready=True,
                detail="installed",
                remedy="",
            )
        ]
        with (
            patch(
                "debugoracle.cli.commands.docs_cli.collect_docs_doctor_checks",
                return_value=checks_ready,
            ),
            patch("debugoracle.cli.commands.docs_cli.emit"),
        ):
            code = docs_cli.cmd_docs_doctor(SimpleNamespace(format="text", output=None))
        self.assertEqual(code, 0)


class StatusCaptureEmitTests(unittest.TestCase):
    def test_emit_prints_or_writes_file(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = status_capture.emit("hello\n", None)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "hello\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "out" / "status.txt"
            code = status_capture.emit("data", str(target))
            self.assertEqual(code, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "data")


if __name__ == "__main__":
    unittest.main()
