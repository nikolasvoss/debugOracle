from __future__ import annotations

import json
import builtins
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from debugoracle.cli import main
from debugoracle.cli.commands.docs_cli import _render_ingest, _run_docs_ingest
from debugoracle.cli.main import build_parser
from debugoracle.docs_sidecar import (
    ENVELOPE_FILENAME,
    STAGING_SUFFIX,
    DocsArtifact,
    DocsChunk,
    DocsEnvelope,
    DocsIngestBatch,
    DocsIngestResult,
    DocsIndexEntry,
    DocsParseResult,
    PlainTextParser,
    DoclingParser,
    compute_source_hash,
    discover_candidate_documents,
    ingest_documents,
    is_ingest_fresh,
    load_docs_artifact,
    parse_markdown_table,
    save_docs_artifact,
    search_documents,
    sidecar_dir_for,
    split_markdown_by_headings,
    status_documents,
)


class DocsSidecarTests(unittest.TestCase):
    def test_docs_command_parses_new_flags(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            [
                "docs",
                "ingest",
                "--file",
                "manual.txt",
                "--parser",
                "pymupdf",
                "--semantic",
                "--force",
                "--no-interactive",
            ]
        )

        self.assertEqual(parsed.command, "docs")
        self.assertEqual(parsed.docs_command, "ingest")
        self.assertEqual(parsed.file, ["manual.txt"])
        self.assertEqual(parsed.parser, "pymupdf")
        self.assertTrue(parsed.semantic)
        self.assertTrue(parsed.force)
        self.assertTrue(parsed.no_interactive)

    def test_docs_doctor_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["docs", "doctor", "--format", "json"])

        self.assertEqual(parsed.command, "docs")
        self.assertEqual(parsed.docs_command, "doctor")
        self.assertEqual(parsed.format, "json")

    def test_docs_search_parses_semantic_flag(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["docs", "search", "USART", "--semantic"])

        self.assertTrue(parsed.semantic)

    def test_ingest_explicit_text_file_writes_extended_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text(
                "USART1 CR1 register enables transmitter.\n", encoding="utf-8"
            )
            expected_hash = compute_source_hash(manual.resolve())

            batch = ingest_documents(workspace_root=tmpdir, files=[str(manual)])
            artifact = load_docs_artifact(sidecar_dir_for(manual))

        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].ingest_state, "clean")
        self.assertEqual(artifact.envelope.source_pdf, str(manual.resolve()))
        self.assertEqual(artifact.envelope.parser_used, "plain-text")
        self.assertEqual(artifact.envelope.chunk_count, 1)
        self.assertEqual(artifact.index_entries[0].page_start, 1)
        self.assertIn("usart1", artifact.index_entries[0].tokens)
        self.assertEqual(artifact.envelope.source_hash, expected_hash)
        self.assertFalse(artifact.envelope.semantic_indexed)

    def test_staleness_detection_skips_fresh_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOA MODER register.\n", encoding="utf-8")

            first = ingest_documents(workspace_root=tmpdir, files=[str(manual)])
            second = ingest_documents(workspace_root=tmpdir, files=[str(manual)])

        self.assertFalse(first.results[0].skipped)
        self.assertTrue(second.results[0].skipped)

    def test_staleness_skip_preserves_existing_ingest_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOA MODER register.\n", encoding="utf-8")
            ingest_documents(workspace_root=tmpdir, files=[str(manual)])

            sidecar = sidecar_dir_for(manual)
            envelope_path = sidecar / ENVELOPE_FILENAME
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            envelope["ingest_state"] = "warning"
            envelope["warning_summary"] = "existing warning"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

            second = ingest_documents(workspace_root=tmpdir, files=[str(manual)])

        self.assertTrue(second.results[0].skipped)
        self.assertEqual(second.results[0].ingest_state, "warning")
        self.assertEqual(second.results[0].warning_summary, "existing warning")

    def test_staleness_failed_envelope_forces_reingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOA MODER register.\n", encoding="utf-8")
            ingest_documents(workspace_root=tmpdir, files=[str(manual)])

            sidecar = sidecar_dir_for(manual)
            envelope_path = sidecar / ENVELOPE_FILENAME
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            envelope["ingest_state"] = "failed"
            envelope["warning_summary"] = "old failure"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

            second = ingest_documents(workspace_root=tmpdir, files=[str(manual)])

        self.assertFalse(second.results[0].skipped)
        self.assertNotEqual(second.results[0].ingest_state, "failed")

    def test_force_flag_bypasses_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOA MODER register.\n", encoding="utf-8")

            ingest_documents(workspace_root=tmpdir, files=[str(manual)])
            forced = ingest_documents(
                workspace_root=tmpdir, files=[str(manual)], force=True
            )

        self.assertFalse(forced.results[0].skipped)

    def test_staleness_detection_reingest_on_parser_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "manual.pdf"
            source.write_bytes(b"%PDF-1.4")
            sidecar = sidecar_dir_for(source)
            sidecar.mkdir(parents=True)
            envelope = {
                "source_pdf": str(source.resolve()),
                "parser_used": "docling",
                "derived_paths": [
                    str(sidecar / ENVELOPE_FILENAME),
                    str(sidecar / "index.json"),
                ],
                "page_count": 1,
                "chunk_count": 1,
                "warning_summary": "",
                "ingest_state": "clean",
                "source_hash": compute_source_hash(source.resolve()),
                "semantic_indexed": False,
            }
            (sidecar / ENVELOPE_FILENAME).write_text(
                json.dumps(envelope), encoding="utf-8"
            )
            (sidecar / "index.json").write_text("[]", encoding="utf-8")

            fresh = is_ingest_fresh(source.resolve(), sidecar, parser_name="pymupdf")

        self.assertFalse(fresh)

    def test_legacy_sidecar_missing_hash_triggers_reingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "manual.pdf"
            source.write_bytes(b"%PDF-1.4")
            sidecar = sidecar_dir_for(source)
            sidecar.mkdir(parents=True)
            envelope = {
                "source_pdf": str(source.resolve()),
                "parser_used": "pymupdf",
                "derived_paths": [
                    str(sidecar / ENVELOPE_FILENAME),
                    str(sidecar / "index.json"),
                ],
                "page_count": 1,
                "chunk_count": 1,
                "warning_summary": "",
                "ingest_state": "clean",
            }
            (sidecar / ENVELOPE_FILENAME).write_text(
                json.dumps(envelope), encoding="utf-8"
            )
            (sidecar / "index.json").write_text("[]", encoding="utf-8")

            fresh = is_ingest_fresh(source.resolve(), sidecar, parser_name="pymupdf")

        self.assertFalse(fresh)

    def test_failed_sidecar_is_not_fresh_even_when_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "manual.pdf"
            source.write_bytes(b"%PDF-1.4")
            sidecar = sidecar_dir_for(source)
            sidecar.mkdir(parents=True)
            envelope = {
                "source_pdf": str(source.resolve()),
                "parser_used": "pymupdf",
                "derived_paths": [
                    str(sidecar / ENVELOPE_FILENAME),
                    str(sidecar / "index.json"),
                ],
                "page_count": 1,
                "chunk_count": 0,
                "warning_summary": "failed run",
                "ingest_state": "failed",
                "source_hash": compute_source_hash(source.resolve()),
                "semantic_indexed": False,
            }
            (sidecar / ENVELOPE_FILENAME).write_text(
                json.dumps(envelope), encoding="utf-8"
            )
            (sidecar / "index.json").write_text("[]", encoding="utf-8")

            fresh = is_ingest_fresh(source.resolve(), sidecar, parser_name="pymupdf")

        self.assertFalse(fresh)

    def test_parse_markdown_table(self) -> None:
        text = """
| Register | Bits |
|---|---|
| USART_BRR | baud divider |
""".strip()

        rows = parse_markdown_table(text)

        self.assertEqual(rows, [["Register", "Bits"], ["USART_BRR", "baud divider"]])

    def test_parse_markdown_table_returns_none_for_no_table(self) -> None:
        self.assertIsNone(parse_markdown_table("No table here."))

    def test_split_markdown_by_headings_builds_heading_path(self) -> None:
        md = """
<!-- Page 1 -->
# Peripherals
## USART
USART section text.
| Name | Value |
|---|---|
| BRR | baud |
""".strip()

        chunks, warnings = split_markdown_by_headings(md, Path("manual.pdf"), doc=None)

        self.assertEqual(warnings, [])
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].heading_path, "Peripherals / USART")
        self.assertEqual(chunks[0].chunk_type, "mixed")
        self.assertIsNotNone(chunks[0].table_rows)

    def test_page_marker_flush_uses_previous_page_end(self) -> None:
        md = """
<!-- Page 1 -->
# First
first-page text
<!-- Page 2 -->
## Second
second-page text
""".strip()

        chunks, _ = split_markdown_by_headings(md, Path("manual.pdf"), doc=None)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].page_start, 1)
        self.assertEqual(chunks[0].page_end, 1)
        self.assertEqual(chunks[1].page_start, 2)

    def test_fallback_chunk_when_no_headings(self) -> None:
        chunks, warnings = split_markdown_by_headings(
            "plain markdown body", Path("manual.pdf"), doc=None
        )

        self.assertEqual(warnings, [])
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "page-1")

    def test_progress_callback_called_during_ingest(self) -> None:
        calls: list[tuple[int, int, str]] = []

        def cb(current: int, total: int, label: str) -> None:
            calls.append((current, total, label))

        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("USART2 BRR register.\n", encoding="utf-8")
            ingest_documents(workspace_root=tmpdir, files=[str(manual)], progress_cb=cb)

        self.assertEqual(calls[0][:2], (0, 1))
        self.assertEqual(calls[-1][:2], (1, 1))

    def test_search_hit_carries_heading_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("unused", encoding="utf-8")
            sidecar = sidecar_dir_for(manual)
            artifact = DocsArtifact(
                envelope=DocsEnvelope(
                    source_pdf=str(manual.resolve()),
                    parser_used="plain-text",
                    derived_paths=[
                        str(sidecar / ENVELOPE_FILENAME),
                        str(sidecar / "index.json"),
                    ],
                    page_count=1,
                    chunk_count=1,
                    warning_summary="",
                    ingest_state="clean",
                    source_hash="hash",
                    semantic_indexed=False,
                    warnings=[],
                ),
                index_entries=[
                    DocsIndexEntry(
                        chunk_id="sec-usart",
                        source_pdf=str(manual.resolve()),
                        page_start=1,
                        page_end=1,
                        text="USART baud rate register",
                        tokens=["usart", "baud", "rate", "register"],
                        token_count=4,
                        term_freq={"usart": 1, "baud": 1, "rate": 1, "register": 1},
                        heading_path="Peripherals / USART / BRR",
                        chunk_type="prose",
                        table_rows=None,
                    )
                ],
            )
            save_docs_artifact(artifact, sidecar)

            result = search_documents(workspace_root=tmpdir, query="baud")

        self.assertEqual(len(result.hits), 1)
        self.assertEqual(result.hits[0].heading_path, "Peripherals / USART / BRR")

    def test_hybrid_search_blends_bm25_and_cosine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("unused", encoding="utf-8")
            sidecar = sidecar_dir_for(manual)
            artifact = DocsArtifact(
                envelope=DocsEnvelope(
                    source_pdf=str(manual.resolve()),
                    parser_used="plain-text",
                    derived_paths=[
                        str(sidecar / ENVELOPE_FILENAME),
                        str(sidecar / "index.json"),
                    ],
                    page_count=2,
                    chunk_count=2,
                    warning_summary="",
                    ingest_state="clean",
                    source_hash="hash",
                    semantic_indexed=True,
                    warnings=[],
                ),
                index_entries=[
                    DocsIndexEntry(
                        chunk_id="a",
                        source_pdf=str(manual.resolve()),
                        page_start=1,
                        page_end=1,
                        text="USART baud rate register",
                        tokens=["usart", "baud", "rate", "register"],
                        token_count=4,
                        term_freq={"usart": 1, "baud": 1, "rate": 1, "register": 1},
                    ),
                    DocsIndexEntry(
                        chunk_id="b",
                        source_pdf=str(manual.resolve()),
                        page_start=2,
                        page_end=2,
                        text="timer prescaler",
                        tokens=["timer", "prescaler"],
                        token_count=2,
                        term_freq={"timer": 1, "prescaler": 1},
                    ),
                ],
            )
            save_docs_artifact(artifact, sidecar)

            with patch(
                "debugoracle.docs_sidecar._semantic_scores_for_entries",
                return_value=([0.1, 0.95], []),
            ):
                result = search_documents(
                    workspace_root=tmpdir, query="baud", semantic=True
                )

        self.assertEqual(len(result.hits), 2)
        self.assertGreaterEqual(result.hits[0].score, result.hits[1].score)

    def test_discovery_returns_doc_and_docs_pdfs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "docs").mkdir()
            (workspace / "docs" / "ref.pdf").write_bytes(b"%PDF")
            (workspace / "docs" / "notes.txt").write_text("ignore", encoding="utf-8")
            (workspace / "doc").mkdir()
            (workspace / "doc" / "chip.pdf").write_bytes(b"%PDF")

            discovered = discover_candidate_documents(workspace)

        self.assertEqual([path.name for path in discovered], ["chip.pdf", "ref.pdf"])

    def test_ingest_requires_confirmation_for_discovered_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "docs").mkdir()
            (workspace / "docs" / "ref.pdf").write_bytes(b"%PDF-1.4")

            batch = ingest_documents(workspace_root=workspace)

        self.assertTrue(batch.confirmation_required)
        self.assertEqual(batch.results, [])
        self.assertEqual(len(batch.discovered_candidates), 1)

    def test_explicit_missing_file_does_not_fall_back_to_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "docs").mkdir()
            (workspace / "docs" / "ref.pdf").write_bytes(b"%PDF-1.4")

            batch = ingest_documents(workspace_root=workspace, files=["missing.pdf"])

        self.assertEqual(batch.results, [])
        self.assertEqual(batch.discovered_candidates, [])
        self.assertEqual(len(batch.invalid_inputs), 1)
        self.assertIn("Explicit file input was not found", batch.warnings[0])

    def test_pdf_plaintext_parser_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "manual.pdf"
            source.write_bytes(b"%PDF-1.4")

            batch = ingest_documents(
                workspace_root=tmpdir,
                files=[str(source)],
                parser_name="plaintext",
            )

        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].ingest_state, "failed")
        self.assertIn(
            "not supported for PDF ingestion", batch.results[0].warning_summary
        )

    def test_search_surfaces_sidecar_load_warning_instead_of_hiding_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("USART1 BRR register.\n", encoding="utf-8")
            sidecar = sidecar_dir_for(manual)
            sidecar.mkdir(parents=True)
            (sidecar / ENVELOPE_FILENAME).write_text("{not-json", encoding="utf-8")
            (sidecar / "index.json").write_text("[]", encoding="utf-8")

            result = search_documents(workspace_root=tmpdir, query="USART1")

        self.assertEqual(result.hits, [])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Corrupt docs envelope", result.warnings[0])

    def test_status_reports_corrupt_envelope_as_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("ADC1 SMPR1 register.\n", encoding="utf-8")
            sidecar = sidecar_dir_for(manual)
            sidecar.mkdir(parents=True)
            (sidecar / ENVELOPE_FILENAME).write_text("{not-json", encoding="utf-8")
            (sidecar / "index.json").write_text("[]", encoding="utf-8")

            statuses = status_documents(workspace_root=tmpdir)

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].ingest_state, "failed")
        self.assertIn("Expecting property name", statuses[0].warning_summary)

    def test_cli_docs_search_json_returns_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOB ODR register.\n", encoding="utf-8")
            ingest_documents(workspace_root=tmpdir, files=[str(manual)])

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = main(
                    [
                        "docs",
                        "search",
                        "GPIOB",
                        "--workspace-root",
                        tmpdir,
                        "--format",
                        "json",
                    ]
                )
            stdout = stdout_buffer.getvalue()
            stderr = stderr_buffer.getvalue()
            payload = json.loads(stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["results"][0]["source_pdf"], str(manual.resolve()))

    def test_cli_docs_ingest_docling_hint_on_pymupdf_warning(self) -> None:
        batch = DocsIngestBatch(
            results=[
                DocsIngestResult(
                    source_pdf="/tmp/ref.pdf",
                    sidecar_dir="/tmp/ref.pdf.dbgoracle-docs",
                    parser_used="pymupdf",
                    page_count=2,
                    chunk_count=2,
                    ingest_state="warning",
                    warning_summary="some warning",
                )
            ],
            discovered_candidates=[],
        )

        with patch(
            "debugoracle.cli.commands.docs_cli._docling_installed", return_value=False
        ):
            rendered = _render_ingest(batch, fmt="text")

        self.assertIn("hint: extraction quality may improve with Docling", rendered)
        self.assertIn("pipx inject debugoracle docling", rendered)
        self.assertIn("pip install 'debugoracle[docling]'", rendered)

    def test_cli_docs_doctor_json_returns_summary(self) -> None:
        stdout_buffer = StringIO()
        stderr_buffer = StringIO()
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exit_code = main(["docs", "doctor", "--format", "json"])
        payload = json.loads(stdout_buffer.getvalue())

        self.assertIn(exit_code, (0, 1, 2))
        self.assertEqual(stderr_buffer.getvalue(), "")
        self.assertIn("checks", payload)
        self.assertIn("summary", payload)

    def test_run_docs_ingest_interactive_confirmation_retries_with_yes(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["docs", "ingest", "--workspace-root", "."])
        first = DocsIngestBatch(
            results=[],
            discovered_candidates=["/tmp/a.pdf"],
            warnings=["re-run with --yes"],
            confirmation_required=True,
        )
        second = DocsIngestBatch(
            results=[
                DocsIngestResult(
                    source_pdf="/tmp/a.pdf",
                    sidecar_dir="/tmp/a.pdf.dbgoracle-docs",
                    parser_used="pymupdf",
                    page_count=1,
                    chunk_count=1,
                    ingest_state="clean",
                    warning_summary="",
                )
            ],
            discovered_candidates=["/tmp/a.pdf"],
        )
        with (
            patch(
                "debugoracle.cli.commands.docs_cli.ingest_documents",
                side_effect=[first, second],
            ) as mocked_ingest,
            patch(
                "debugoracle.cli.commands.docs_cli._interactive_enabled",
                return_value=True,
            ),
            patch("builtins.input", return_value="y"),
        ):
            batch = _run_docs_ingest(args, progress_cb=None)

        self.assertEqual(batch.results[0].ingest_state, "clean")
        self.assertEqual(mocked_ingest.call_count, 2)
        self.assertTrue(mocked_ingest.call_args.kwargs["confirm_discovered"])

    def test_resume_reuses_staged_parse_after_semantic_failure(self) -> None:
        calls: list[int] = []

        def fake_parse(
            self: PlainTextParser, source: Path, *, progress_cb=None
        ) -> DocsParseResult:
            calls.append(1)
            return DocsParseResult(
                chunks=[
                    DocsChunk(
                        chunk_id="page-1",
                        heading_path="",
                        chunk_type="prose",
                        page_start=1,
                        page_end=1,
                        text="USART2 BRR register",
                    )
                ],
                parser_used="plain-text",
                warnings=[],
                page_count=1,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("USART2 BRR register.\n", encoding="utf-8")

            with (
                patch("debugoracle.docs_sidecar.PlainTextParser.parse", new=fake_parse),
                patch(
                    "debugoracle.docs_sidecar.encode_embeddings",
                    side_effect=[RuntimeError("semantic failed"), [[0.0]]],
                ),
                patch(
                    "debugoracle.docs_sidecar.save_embeddings",
                    side_effect=lambda sidecar_dir, _: (
                        Path(sidecar_dir) / "embeddings.npy"
                    ).write_bytes(b"x"),
                ),
            ):
                first = ingest_documents(
                    workspace_root=tmpdir, files=[str(manual)], semantic=True
                )
                second = ingest_documents(
                    workspace_root=tmpdir, files=[str(manual)], semantic=True
                )

            sidecar = sidecar_dir_for(manual)
            staging = sidecar.with_name(f"{sidecar.name}{STAGING_SUFFIX}")

        self.assertEqual(first.results[0].ingest_state, "failed")
        self.assertIn(second.results[0].ingest_state, {"clean", "warning", "partial"})
        self.assertEqual(len(calls), 1)
        self.assertFalse(staging.exists())

    def test_docling_import_failure_surfaces_nested_module_reason(self) -> None:
        parser = DoclingParser()
        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: object = None,
            locals: object = None,
            fromlist: object = (),
            level: int = 0,
        ) -> object:
            if name == "docling.document_converter":
                error = ModuleNotFoundError("No module named 'rapidocr'")
                error.name = "rapidocr"
                raise error
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(RuntimeError) as ctx:
                parser.parse(Path("/tmp/example.pdf"))

        self.assertIn("Docling import failed", str(ctx.exception))
        self.assertIn("rapidocr", str(ctx.exception))

    def test_docling_missing_module_message_includes_pipx_and_venv_paths(self) -> None:
        parser = DoclingParser()
        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: object = None,
            locals: object = None,
            fromlist: object = (),
            level: int = 0,
        ) -> object:
            if name == "docling.document_converter":
                error = ModuleNotFoundError("No module named 'docling'")
                error.name = "docling"
                raise error
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(RuntimeError) as ctx:
                parser.parse(Path("/tmp/example.pdf"))

        message = str(ctx.exception)
        self.assertIn("pipx inject debugoracle docling", message)
        self.assertIn("pip install 'debugoracle[docling]'", message)


if __name__ == "__main__":
    unittest.main()
