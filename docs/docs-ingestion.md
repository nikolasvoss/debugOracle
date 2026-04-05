# Docs Ingestion Guide

Use `dbgoracle docs` to ingest MCU manuals/datasheets into local sidecar artifacts, then search them locally during debugging.

## What You Need

Base requirements:

- Python 3.10+
- Installed `dbgoracle` CLI

If you installed with `./scripts/install/linux.sh`, setup now offers an interactive optional docs-tooling step (`docling`, `semantic`, or both).

Included by default in packaged installs (no extra install needed for normal PDF ingest):

- `pymupdf`
- `pymupdf4llm`

Optional extras:

- Docling parser (better extraction on hard PDFs, scanned docs):
  - primary: `./scripts/install/linux.sh --docs-tools docling`
  - fallback: `pipx inject debugoracle docling`
- Semantic search embeddings:
  - primary: `./scripts/install/linux.sh --docs-tools semantic`
  - fallback: `pipx inject debugoracle sentence-transformers numpy`

If your distro enforces PEP 668 (`error: externally-managed-environment`), install into an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install debugoracle pymupdf pymupdf4llm
```

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

Check docs tooling readiness:

```bash
dbgoracle docs doctor
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
  [--no-interactive] \
  [--format text|json]
```

Search:

```bash
dbgoracle docs search "<query>" \
  [--workspace-root .] \
  [--file <path> ...] \
  [--limit N] \
  [--format text|json]
```

Status:

```bash
dbgoracle docs status \
  [--workspace-root .] \
  [--file <path> ...] \
  [--format text|json]
```

Doctor:

```bash
dbgoracle docs doctor [--format text|json]
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

2. Search (auto-selects hybrid ranking when embeddings are available):

```bash
dbgoracle docs search "serial port speed configuration"
```

If semantic dependencies or embeddings are unavailable, search falls back to BM25 and reports warnings.

## Re-ingest and Staleness

Ingest skips unchanged sources automatically (hash + parser + semantic compatibility check).

If ingest fails partway through, DebugOracle keeps deterministic staging checkpoints and can resume compatible reruns instead of restarting from zero.

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

- install/reinstall base deps (`pymupdf`, `pymupdf4llm`) in your active venv/pipx environment

Docling not installed:

- primary: `./scripts/install/linux.sh --docs-tools docling`
- if using pipx directly: `pipx inject debugoracle docling`
- otherwise install `debugoracle[docling]` in the active environment

Semantic mode not available:

- primary: `./scripts/install/linux.sh --docs-tools semantic`
- if using pipx directly: `pipx inject debugoracle sentence-transformers numpy`
- otherwise install `debugoracle[semantic]` in the active environment

No search results:

- run `dbgoracle docs status` and check for `failed`/`partial`
- try `--parser docling` for difficult PDFs
- use exact register/peripheral terms first; search auto-selects hybrid mode when semantic embeddings are available
- run `dbgoracle docs doctor` to verify parser/semantic dependency readiness
