# docs_sidecar

- Module: `docs_sidecar`
- Code Path: `debugoracle/docs_sidecar.py`
- Public Entrypoints: `ingest_documents`, `search_documents`, `status_documents`
- Last Updated: `2026-08-13`

# SPEC: Local Docs Sidecar

## Purpose

Provide deterministic local document ingestion and search for manuals/datasheets with quality and provenance surfaced in sidecar artifacts.

## Responsibilities

- Resolve explicit files/folders relative to a workspace root.
- Discover likely PDFs under `doc/` and `docs/` when no explicit inputs are supplied.
- Parse PDFs with pluggable parsers (`pypdf` default, optional `docling`) and text files with `plaintext` parser.
- Build structural chunks (heading-aware when available) and persist BM25-ready index entries.
- Preserve compatibility with legacy sidecars via defaulted `from_dict()` fields.
- Optionally build semantic embeddings (`embeddings.npy`) for hybrid search.
- Skip ingest when source hash + parser + semantic requirements are unchanged, unless forced.
- Support resumable ingest through explicit staging checkpoints and atomic sidecar publish.

## PDF Parser Contract

- `pypdf` is the default PDF parser and processes pages in source order.
- Every extracted chunk retains one-based `page_start` and `page_end` provenance.
- Page text is normalized deterministically before indexing.
- Encrypted and unreadable PDFs fail explicitly without fabricated text or a silent parser switch.
- Empty and image-only pages produce distinct warnings and count as empty-page evidence.
- When Docling page provenance is untrusted, ingestion explicitly retries with `pypdf`. If that fallback fails, the original Docling chunks remain the persisted evidence and the warning records the failed fallback.

## Canonical Envelope Contract

Every ingest writes `envelope.json` with at least:

- `source_pdf`
- `parser_used`
- `derived_paths`
- `page_count`
- `chunk_count`
- `warning_summary`
- `ingest_state`
- `source_hash`
- `semantic_indexed`

## Storage Contract

- Sidecar artifacts live in a sibling directory named `<source-name>.dbgoracle-docs`.
- Agent-driven automatic workspace initialization stores new artifacts below
  `.dbgoracle/documentation-search/`; direct document commands retain sibling
  storage for compatibility. Search and status read both locations.
- Sidecars contain `envelope.json` and `index.json`.
- Optional `embeddings.npy` is written when semantic indexing is enabled.
- `index.json` stores chunk entries with text/tokens and structural metadata (`heading_path`, `chunk_type`, optional `table_rows`).
- In-progress checkpoint artifacts are stored in a sibling staging directory and are not treated as final sidecars.

## Quality Policy

- `clean`: readable chunks for the parsed inventory with no warnings.
- `warning`: readable chunks for all parsed pages with parser warnings.
- `partial`: chunk coverage incomplete or empty-page evidence exists.
- `failed`: no usable page/chunk inventory was produced.

## Search Contract

- BM25-style ranking is always available.
- Semantic mode blends normalized BM25 and cosine scores when embeddings are available.
- If semantic dependencies or embeddings are missing/corrupt, search falls back to BM25 and reports warnings.

## Acceptance Criteria

- `AC-DOCS-001`: The parser factory and CLI expose `pypdf` as the default PDF backend and reject the removed backend name.
- `AC-DOCS-002`: PDF extraction returns normalized page chunks in source order with one-based provenance.
- `AC-DOCS-003`: Encrypted, unreadable, empty, and image-only PDFs surface explicit failure or quality semantics.
- `AC-DOCS-004`: Failed Docling-to-pypdf fallback preserves the original Docling evidence and records the fallback failure.

## Validation Mapping

| Acceptance Criterion | Validation |
|---|---|
| `AC-DOCS-001` | `tests.test_docs_sidecar.DocsSidecarTests.test_docs_ingest_defaults_to_pypdf_and_rejects_removed_backend` |
| `AC-DOCS-002` | `tests.test_docs_sidecar.DocsSidecarTests.test_pypdf_extracts_normalized_pages_in_source_order_with_provenance` |
| `AC-DOCS-003` | pypdf encrypted, malformed, empty-page, and image-only tests in `tests.test_docs_sidecar` |
| `AC-DOCS-004` | `tests.test_docs_sidecar.DocsSidecarTests.test_docling_collapsed_mapping_with_failed_fallback_is_partial` |
