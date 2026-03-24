from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from debugoracle.cli import main
from debugoracle.cli.main import build_parser
from debugoracle.docs_sidecar import (
    ENVELOPE_FILENAME,
    DocsArtifact,
    DocsEnvelope,
    DocsIndexEntry,
    discover_candidate_documents,
    ingest_documents,
    load_docs_artifact,
    save_docs_artifact,
    search_documents,
    sidecar_dir_for,
    status_documents,
)


class DocsSidecarTests(unittest.TestCase):
    def test_docs_command_parses(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["docs", "ingest", "--file", "manual.txt"])

        self.assertEqual(parsed.command, "docs")
        self.assertEqual(parsed.docs_command, "ingest")
        self.assertEqual(parsed.file, ["manual.txt"])

    def test_ingest_explicit_text_file_writes_canonical_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("USART1 CR1 register enables transmitter.\n", encoding="utf-8")

            batch = ingest_documents(workspace_root=tmpdir, files=[str(manual)])
            artifact = load_docs_artifact(sidecar_dir_for(manual))

        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].ingest_state, "clean")
        self.assertEqual(artifact.envelope.source_pdf, str(manual.resolve()))
        self.assertEqual(artifact.envelope.parser_used, "plain-text")
        self.assertEqual(artifact.envelope.chunk_count, 1)
        self.assertEqual(artifact.index_entries[0].page_start, 1)
        self.assertIn("usart1", artifact.index_entries[0].tokens)

    def test_folder_ingest_collects_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "manuals"
            docs_dir.mkdir()
            (docs_dir / "a.txt").write_text("GPIOA MODER register.\n", encoding="utf-8")
            (docs_dir / "b.md").write_text("USART2 baud rate register.\n", encoding="utf-8")
            (docs_dir / "ignore.bin").write_bytes(b"\x00\x01")

            batch = ingest_documents(workspace_root=tmpdir, folders=[str(docs_dir)])

        self.assertEqual(len(batch.results), 2)
        self.assertEqual({Path(item.source_pdf).name for item in batch.results}, {"a.txt", "b.md"})

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

    def test_discovery_ingest_with_yes_uses_pdf_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "docs").mkdir()
            source = workspace / "docs" / "ref.pdf"
            source.write_bytes(b"%PDF-1.4")

            with patch(
                "debugoracle.docs_sidecar._extract_pdf_pages",
                return_value=(["RCC APB2ENR enables USART1 clock."], "fake-pdf", []),
            ):
                batch = ingest_documents(workspace_root=workspace, confirm_discovered=True)

            artifact = load_docs_artifact(sidecar_dir_for(source))

        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].parser_used, "fake-pdf")
        self.assertEqual(artifact.envelope.ingest_state, "clean")
        self.assertEqual(artifact.index_entries[0].page_start, 1)

    def test_search_surfaces_degraded_result_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("TIM2 PSC prescaler register.\n", encoding="utf-8")
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
                    warning_summary="Page 1 extracted no text in one section.",
                    ingest_state="partial",
                    warnings=["Page 1 extracted no text in one section."],
                ),
                index_entries=[
                    DocsIndexEntry(
                        chunk_id="page-1",
                        source_pdf=str(manual.resolve()),
                        page_start=1,
                        page_end=1,
                        text="TIM2 PSC prescaler register.",
                        tokens=["tim2", "psc", "prescaler", "register"],
                        token_count=4,
                        term_freq={"tim2": 1, "psc": 1, "prescaler": 1, "register": 1},
                    )
                ],
            )
            save_docs_artifact(artifact, sidecar)

            result = search_documents(workspace_root=tmpdir, query="TIM2 PSC")

        self.assertEqual(len(result.hits), 1)
        self.assertEqual(result.hits[0].ingest_state, "partial")
        self.assertIn("Page 1 extracted no text", result.hits[0].warning_summary)

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

    def test_status_reports_not_yet_ingested_file_without_calling_it_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("ADC1 SMPR1 register.\n", encoding="utf-8")

            statuses = status_documents(workspace_root=tmpdir, files=[str(manual)])

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].ingest_state, "failed")
        self.assertIn("Run `dbgoracle docs ingest` first", statuses[0].warning_summary)
        self.assertNotIn("Corrupt docs envelope", statuses[0].warning_summary)

    def test_cli_docs_search_json_returns_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOB ODR register.\n", encoding="utf-8")
            ingest_documents(workspace_root=tmpdir, files=[str(manual)])

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = main(
                    ["docs", "search", "GPIOB", "--workspace-root", tmpdir, "--format", "json"]
                )
            stdout = stdout_buffer.getvalue()
            stderr = stderr_buffer.getvalue()
            payload = json.loads(stdout)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["results"][0]["source_pdf"], str(manual.resolve()))

    def test_cli_docs_search_returns_warning_payload_for_corrupt_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual = Path(tmpdir) / "manual.txt"
            manual.write_text("GPIOB ODR register.\n", encoding="utf-8")
            sidecar = sidecar_dir_for(manual)
            sidecar.mkdir(parents=True)
            (sidecar / ENVELOPE_FILENAME).write_text("{not-json", encoding="utf-8")
            (sidecar / "index.json").write_text("[]", encoding="utf-8")

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = main(
                    ["docs", "search", "GPIOB", "--workspace-root", tmpdir, "--format", "json"]
                )
            payload = json.loads(stdout_buffer.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["results"], [])
        self.assertEqual(len(payload["warnings"]), 1)
        self.assertIn("Corrupt docs envelope", payload["warnings"][0])

    def test_cli_docs_ingest_returns_failure_for_missing_explicit_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "docs").mkdir()
            (workspace / "docs" / "ref.pdf").write_bytes(b"%PDF-1.4")

            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exit_code = main(
                    ["docs", "ingest", "--workspace-root", tmpdir, "--file", "missing.pdf", "--format", "json"]
                )
            payload = json.loads(stdout_buffer.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["discovered_candidates"], [])
        self.assertEqual(len(payload["invalid_inputs"]), 1)
