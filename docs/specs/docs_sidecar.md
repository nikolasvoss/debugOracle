# docs_sidecar

- Module: `docs_sidecar`
- Code Path: `debugoracle/docs_sidecar.py`
- Public Entrypoints: `ingest_documents`, `search_documents`, `status_documents`
- Last Updated: `2026-03-24`

# SPEC: Local Docs Sidecar

## Purpose

Provide a bounded local document-ingestion sidecar for manuals and datasheets used during embedded debugging.

## Responsibilities

- Resolve explicit document files or folders relative to a workspace root.
- Discover likely PDFs under `doc/` and `docs/` only when the user has not provided explicit inputs.
- Persist a tiny canonical envelope plus local search index beside each source document.
- Surface parser quality honestly through `clean`, `warning`, `partial`, and `failed` ingest states.
- Provide exact-term-friendly local search over ingested chunks without any hosted dependency.

## Canonical Envelope Contract

Every ingest writes an `envelope.json` with at least:

- `source_pdf`
- `parser_used`
- `derived_paths`
- `page_count`
- `chunk_count`
- `warning_summary`
- `ingest_state`

The envelope may carry extra detail like raw warning strings, but search and status rely only on the stable fields above.

## Storage Contract

- Sidecar artifacts live in a sibling directory named `<source-name>.dbgoracle-docs`.
- Each sidecar contains `envelope.json` and `index.json`.
- `index.json` stores page-level chunks and token statistics for local BM25-style ranking.

## Quality Policy

- `clean`: pages produced searchable chunks and no warnings were recorded.
- `warning`: searchable chunks exist for every page, but parser warnings were recorded.
- `partial`: only a subset of pages became searchable chunks, or text was missing from parts of the document.
- `failed`: no page inventory could be produced at all.

