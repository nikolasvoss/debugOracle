# docs_cli

- Module: `docs_cli`
- Code Path: `debugoracle/cli/commands/docs_cli.py`
- Public Entrypoints: `cmd_docs_ingest`, `cmd_docs_search`, `cmd_docs_status`, `cmd_docs_doctor`
- Last Updated: `2026-03-27`

# SPEC: Docs CLI Commands

## Purpose

Expose local docs sidecar ingest/search/status workflows with deterministic text/JSON output and stable exit codes.

## Responsibilities

- Render `docs ingest`, `docs search`, `docs status`, and `docs doctor` in text or JSON.
- Preserve explicit confirmation flow for auto-discovered PDFs (`--yes` required).
- Allow interactive confirmation prompts for `docs ingest` in TTY text mode, with `--no-interactive` override.
- Forward parser and indexing options to the sidecar layer:
  - ingest: `--parser`, `--semantic`, `--force`, `--no-interactive`
  - search: `--semantic`
- Show ingest progress in text mode, including long-run heartbeat labels for coarse parser phases.
- Surface Docling install/use hints when PyMuPDF quality is degraded.
- Surface deterministic docs dependency diagnostics via `docs doctor`.

## Exit Code Contract

- `docs ingest` returns `0` for clean or warning-only ingests, `2` when confirmation is required or any ingest is partial, and `1` when all selected work fails.
- `docs search` returns `0` when hits are found, `1` when none are found, and `2` when warnings indicate corpus trust issues.
- `docs status` returns `0` when status can be reported without failed artifacts and `1` when nothing is ingested or any artifact is failed/corrupt.
- `docs doctor` returns `0` when required docs dependencies are ready, `1` when required dependencies are missing, and `2` when required dependencies are ready but optional extras are missing.
