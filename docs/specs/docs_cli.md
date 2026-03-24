# docs_cli

- Module: `docs_cli`
- Code Path: `debugoracle/cli/commands/docs_cli.py`
- Public Entrypoints: `cmd_docs_ingest`, `cmd_docs_search`, `cmd_docs_status`
- Last Updated: `2026-03-24`

# SPEC: Docs CLI Commands

## Purpose

Expose the local docs-sidecar workflow on the public `dbgoracle docs` command surface.

## Responsibilities

- Render `docs ingest`, `docs search`, and `docs status` results in text or JSON form.
- Preserve explicit confirmation for auto-discovered PDFs by returning a non-zero status and a candidate list until `--yes` is provided.
- Keep product logic in `debugoracle/docs_sidecar.py`; this module is formatting and exit-code glue.

## Exit Code Contract

- `docs ingest` returns `0` for clean or warning-only ingests, `2` when confirmation is required or any ingest is partial, and `1` when all selected work fails.
- `docs search` returns `0` when hits are found, `1` when none are found, and `2` when search cannot trust the corpus because sidecar warnings or corrupt artifacts were surfaced.
- `docs status` returns `0` when status can be reported without failed artifacts and `1` when nothing is ingested or any artifact is failed/corrupt.
