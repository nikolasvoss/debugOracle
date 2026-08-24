# Docs Ingestion Guide

Use `dbgoracle docs` to ingest MCU manuals/datasheets into local sidecar artifacts, then search them locally during debugging.

## What You Need

Base requirements:

- Python 3.10–3.14
- Installed `dbgoracle` CLI

The Linux installer uses the base profile. Docling, semantic, and combined
profiles are disabled for the currently supported installer because their direct
dependency and model license audits are incomplete.

Included by default in packaged installs (no extra install needed for normal PDF ingest):

- `pypdf`

Optional package extras remain declared for downstream experimentation, but
they are outside the currently supported install path. See the Python dependency
inventory linked from `THIRD_PARTY_NOTICES.md` before selecting them manually.

If your distro enforces PEP 668 (`error: externally-managed-environment`), install into an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install debugoracle pypdf
```

Docling can download model assets. No Docling/model combination is selected by
the supported installer until its licenses have been inventoried and reviewed.

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
  [--parser pypdf|docling] \
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

- `--parser pypdf` (default)
- `--parser docling` (optional extra)

Example:

```bash
dbgoracle docs ingest --file doc/STM32F4_Reference_Manual.pdf --parser docling
```

The default `pypdf` backend extracts normalized text page-by-page in source
order and records one-based page provenance. Empty and image-only pages are
reported explicitly and make an otherwise usable ingest `partial`. Encrypted
or malformed PDFs fail explicitly without switching parsers or fabricating
text.

Docling is an experimental optional backend outside the supported 0.3.0 install
path. Its dependency and model license audits are not complete. When an
independently prepared environment uses it and its page mapping cannot be
trusted, DebugOracle reports the condition and explicitly retries with
`pypdf`. If that fallback fails, the original Docling evidence is retained with
a warning describing the failure.

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

pypdf import/install issue:

- install/reinstall `pypdf` in your active venv/pipx environment

Docling not installed:

- the Docling profile is intentionally unavailable in the currently supported installer
- use the base `pypdf` parser

Semantic mode not available:

- the semantic profile is intentionally unavailable in the currently supported installer
- base BM25 search remains available

No search results:

- run `dbgoracle docs status` and check for `failed`/`partial`
- use the supported `pypdf` parser; the Docling profile remains blocked for this release
- use exact register/peripheral terms first; search auto-selects hybrid mode when semantic embeddings are available
- run `dbgoracle docs doctor` to verify parser/semantic dependency readiness
