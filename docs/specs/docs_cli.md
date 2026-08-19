# docs_cli

- Module: `docs_cli`
- Code Path: `debugoracle/cli/commands/docs_cli.py`
- Public Entrypoints: `cmd_docs_ingest`, `cmd_docs_search`, `cmd_docs_status`, `cmd_docs_doctor`
- Last Updated: `2026-08-19`

# SPEC: Docs CLI Commands

## Purpose

Expose local docs sidecar ingest/search/status workflows with deterministic text/JSON output and stable exit codes.

## Responsibilities

- Render `docs ingest`, `docs search`, `docs status`, and `docs doctor` in text or JSON.
- Preserve explicit confirmation flow for auto-discovered PDFs (`--yes` required).
- Auto-discover only regular, non-symlink PDF files below `doc/` and `docs/`.
  Discovery does not traverse directory symlinks, rejects canonical paths outside
  the workspace, and returns canonical candidates in stable sorted order without
  duplicates.
- Allow interactive confirmation prompts for `docs ingest` in TTY text mode, with `--no-interactive` override.
- Forward parser and indexing options to the sidecar layer:
  - ingest: `--parser`, `--semantic`, `--force`, `--no-interactive`
  - search: `--semantic`
- Show ingest progress in text mode, including long-run heartbeat labels for coarse parser phases.
- Accept `--parser pypdf|docling`, default to `pypdf`, and reject removed parser names.
- Surface Docling install/use hints when pypdf quality is degraded.
- Surface deterministic docs dependency diagnostics via `docs doctor`.

## Acceptance Criteria

- `AC-DOCS-CLI-001`: `docs ingest` defaults to `pypdf`, accepts optional `docling`, and rejects removed parser choices.
- `AC-DOCS-CLI-002`: `docs doctor` reports `pypdf` as the sole required base PDF dependency and contains no removed dependency guidance.
- `AC-DOCS-CLI-003`: automatic PDF discovery remains contained within the
  workspace, excludes file and directory symlinks, and supplies deterministic
  canonical candidates to the ordinary ingest flow.

## Validation Mapping

| Acceptance Criterion | Validation |
|---|---|
| `AC-DOCS-CLI-001` | `tests.test_docs_sidecar.DocsSidecarTests.test_docs_ingest_defaults_to_pypdf_and_rejects_removed_backend` |
| `AC-DOCS-CLI-002` | `tests.test_diagnostics.DocsDiagnosticsTests.test_docs_doctor_requires_pypdf_as_the_only_base_pdf_dependency` |
| `AC-DOCS-CLI-003` | `tests.test_docs_sidecar.DocsSidecarTests.test_discovery_rejects_in_workspace_pdf_symlink_alias`, `tests.test_docs_sidecar.DocsSidecarTests.test_discovery_rejects_pdf_symlink_outside_workspace`, `tests.test_docs_sidecar.DocsSidecarTests.test_discovery_does_not_traverse_symlink_directories`, `tests.test_docs_sidecar.DocsSidecarTests.test_discovered_ingest_never_parses_a_symlinked_pdf` |

## Exit Code Contract

- `docs ingest` returns `0` for clean or warning-only ingests, `2` when confirmation is required or any ingest is partial, and `1` when all selected work fails.
- `docs search` returns `0` when hits are found, `1` when none are found, and `2` when warnings indicate corpus trust issues.
- `docs status` returns `0` when status can be reported without failed artifacts and `1` when nothing is ingested or any artifact is failed/corrupt.
- `docs doctor` returns `0` when required docs dependencies are ready, `1` when required dependencies are missing, and `2` when required dependencies are ready but optional extras are missing.
