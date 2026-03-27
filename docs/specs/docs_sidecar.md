# docs_sidecar

- Module: `docs_sidecar`
- Code Path: `debugoracle/docs_sidecar.py`
- Public Entrypoints: `ingest_documents`, `search_documents`, `status_documents`
- Last Updated: `2026-03-27`

# SPEC: Local Docs Sidecar

## Purpose

Provide deterministic local document ingestion and search for manuals/datasheets with quality and provenance surfaced in sidecar artifacts.

## Responsibilities

- Resolve explicit files/folders relative to a workspace root.
- Discover likely PDFs under `doc/` and `docs/` when no explicit inputs are supplied.
- Parse PDFs with pluggable parsers (`pymupdf` default, optional `docling`) and text files with `plaintext` parser.
- Build structural chunks (heading-aware when available) and persist BM25-ready index entries.
- Preserve compatibility with legacy sidecars via defaulted `from_dict()` fields.
- Optionally build semantic embeddings (`embeddings.npy`) for hybrid search.
- Skip ingest when source hash + parser + semantic requirements are unchanged, unless forced.
- Support resumable ingest through explicit staging checkpoints and atomic sidecar publish.

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
