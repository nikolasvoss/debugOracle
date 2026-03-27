# Docs Ingestion Guide

Use `dbgoracle docs` to ingest MCU manuals/datasheets into local sidecar artifacts, then search them locally during debugging.

## What You Need

Base requirements:

- Python 3.10+
- Installed `dbgoracle` CLI

Included by default (no extra install needed for normal PDF ingest):

- `pymupdf`
- `pymupdf4llm`

Optional extras:

- Docling parser (better extraction on hard PDFs, scanned docs):
  - packaged install: `pip install 'debugoracle[docling]'`
  - local checkout: `pip install '.[docling]'`
- Semantic search embeddings:
  - packaged install: `pip install 'debugoracle[semantic]'`
  - local checkout: `pip install '.[semantic]'`

If you installed with `pipx`, add extras with:

- `pipx inject debugoracle docling`
- `pipx inject debugoracle sentence-transformers numpy`

Docling first run can download large models. For offline/CI usage, pre-populate and point `DOCLING_CACHE_HOME` at a prepared cache.

## Quick Start

Ingest one manual:

```bash
dbgoracle docs ingest --file doc/STM32F4_Reference_Manual.pdf
```

Search:

```bash
dbgoracle docs search "USART baud rate register"
```

Check ingest health:

```bash
dbgoracle docs status
```

## Ingest Inputs

You can ingest with:

- `--file` (repeatable)
- `--folder` (repeatable)

If you pass neither, DebugOracle discovers likely PDFs under `doc/` and `docs/`, then requires explicit confirmation with `--yes`.

Example:

```bash
dbgoracle docs ingest --yes
```

## Command Reference

Ingest:

```bash
dbgoracle docs ingest \
  [--workspace-root .] \
  [--file <path> ...] \
  [--folder <path> ...] \
  [--yes] \
  [--parser pymupdf|docling] \
  [--semantic] \
  [--force] \
  [--format text|json]
```

Search:

```bash
dbgoracle docs search "<query>" \
  [--workspace-root .] \
  [--file <path> ...] \
  [--limit N] \
  [--semantic] \
  [--format text|json]
```

Status:

```bash
dbgoracle docs status \
  [--workspace-root .] \
  [--file <path> ...] \
  [--format text|json]
```

## Parser Choice

`docs ingest` supports:

- `--parser pymupdf` (default)
- `--parser docling` (optional extra)

Example:

```bash
dbgoracle docs ingest --file doc/STM32F4_Reference_Manual.pdf --parser docling
```

## Semantic Search

1. Ingest with embeddings:

```bash
dbgoracle docs ingest --file doc/STM32F4_Reference_Manual.pdf --semantic
```

2. Search with hybrid ranking:

```bash
dbgoracle docs search "serial port speed configuration" --semantic
```

If semantic dependencies or embeddings are unavailable, search falls back to BM25 and reports warnings.

## Re-ingest and Staleness

Ingest skips unchanged sources automatically (hash + parser + semantic compatibility check).

Force re-ingest:

```bash
dbgoracle docs ingest --file doc/STM32F4_Reference_Manual.pdf --force
```

## Where Artifacts Are Written

For a source PDF:

```text
doc/STM32F4_Reference_Manual.pdf
```

DebugOracle writes:

```text
doc/STM32F4_Reference_Manual.pdf.dbgoracle-docs/
  envelope.json
  index.json
  embeddings.npy   # only when --semantic was used
```

## Understanding Ingest States

- `clean`: good ingest, no warnings
- `warning`: ingest succeeded but parser emitted warnings
- `partial`: only part of the document became searchable
- `failed`: ingest failed

`docs search` and `docs status` surface these states and warning summaries so you can judge trust quickly.

## Troubleshooting

PyMuPDF import/install issue:

- reinstall base deps (`pymupdf`, `pymupdf4llm`)

Docling not installed:

- install `debugoracle[docling]` (or `.[docling]` from checkout)

Semantic mode not available:

- install `debugoracle[semantic]` (or `.[semantic]` from checkout)

No search results:

- run `dbgoracle docs status` and check for `failed`/`partial`
- try `--parser docling` for difficult PDFs
- use exact register/peripheral terms first, then add `--semantic` if installed
