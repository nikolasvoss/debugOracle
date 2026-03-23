# evidence

- Module: `evidence`
- Code Path: `debugoracle/cli/commands/evidence.py`
- Public Entrypoints: `cmd_fetch`, `cmd_report`
- Last Updated: `2026-03-22`

# SPEC: DebugOracle Evidence Commands

## Purpose

Own the CLI flows that resolve raw or saved evidence, build or load artifacts, and render them.

## Responsibilities

- Resolve raw evidence for `fetch`.
- Resolve snapshot input for `report`.
- Build investigation artifacts from raw evidence when required.
- Save snapshots for `fetch` and render report output for reuse.
- Keep `fetch` stdout operational by summarizing the saved snapshot as outcome, evidence coverage, and next-step guidance rather than rendering interpretive evidence.
- Thread `report` inspect-mode flags into the renderer layer without rebuilding from raw evidence.

## Boundaries

- Use artifact persistence, pipeline/builder shaping, and renderer modules rather than reimplementing them here.
- Keep command-specific path resolution and CLI messaging here.
- Do not own parser construction; that belongs in `debugoracle/cli/main.py`.

## Command Resolution Contract

- `cmd_fetch` is raw-only and never loads a snapshot as its primary evidence source.
- `cmd_fetch --svd-file <file>` is the only explicit CLI path that enables live peripheral capture; it passes an explicit opt-in through the builder instead of relying on `svd_file_path` alone.
- When no explicit `--svd-file` is provided, `cmd_fetch` may resolve `debugoracle.svdFile` from `.vscode/settings.json` as the workspace default SVD.
- Workspace-default `debugoracle.svdFile` values may be absolute paths, workspace-relative paths, or `${workspaceFolder}`-prefixed paths; `cmd_fetch` normalizes the workspace token before file resolution.
- If neither an explicit nor workspace-default SVD is available, `cmd_fetch` may auto-resolve exactly one `.dbgoracle/*.svd` candidate for opportunistic live peripheral capture. If discovery is ambiguous or live capture fails, plain `fetch` falls back to non-SVD snapshot capture and emits a clear notice on `stderr`.
- `cmd_fetch` accepts optional `--openocd-tcl-host` and `--openocd-tcl-port` overrides for live peripheral capture. If no explicit or auto-resolved SVD is available, plain `fetch` ignores these overrides and continues with non-SVD capture after emitting a notice.
- `cmd_report` is snapshot-only and fails clearly when no snapshot can be resolved.
- `cmd_report` points users to `fetch` when no snapshot is available.

## Report Inspect Contract

- Default `report` output is a concise human-readable summary that starts with an explicit trust verdict, then current state, gaps, and next useful commands.
- When trust is unsafe, default `report` output degrades to a short trust-first report unless `--allow-unsafe` is supplied.
- `report --vars [NAME ...]` emits a compact JSON object under `variables`.
- `report --gdb [--tail N]` emits a compact JSON object under `gdb`.
- `report --rtt [--tail N]` emits a compact JSON object under `rtt`.
- `report --verbose [--tail N]` emits a compact JSON object containing summary, variables, source
  streams, and provenance metadata.
- Combined inspect flags emit one compact JSON object containing only the requested sections plus a top-level `trust` object.
- Inspect payloads that include stream or register sections also include compact snapshot metadata for provenance and freshness.
