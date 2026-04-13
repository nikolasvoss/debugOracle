# evidence

- Module: `evidence`
- Code Path: `debugoracle/cli/commands/evidence.py`
- Public Entrypoints: `cmd_fetch`, `cmd_report`
- Last Updated: `2026-04-13`

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
- Thread explicit memory capture selectors from `fetch --mem` into artifact persistence.

## Boundaries

- Use artifact persistence, pipeline/builder shaping, and renderer modules rather than reimplementing them here.
- Keep command-specific path resolution and CLI messaging here.
- Do not own parser construction; that belongs in `debugoracle/cli/main.py`.

## Command Resolution Contract

- `cmd_fetch` is raw-only and never loads a snapshot as its primary evidence source.
- `cmd_fetch --mem ADDR:SIZE` performs bounded read-only memory capture and stores canonical `sources.memory` entries.
- `cmd_fetch` next-step guidance should stay portable for the active workspace (for example `--workspace-root .`) instead of host-specific absolute workspace paths.
- `cmd_fetch --svd-file <file>` is the only explicit CLI path that enables live peripheral capture; it passes an explicit opt-in through the builder instead of relying on `svd_file_path` alone.
- When no explicit `--svd-file` is provided, `cmd_fetch` may resolve `debugoracle.svdFile` from `.vscode/settings.json` as the workspace default SVD.
- Workspace-default `debugoracle.svdFile` values may be absolute paths, workspace-relative paths, or `${workspaceFolder}`-prefixed paths; `cmd_fetch` normalizes the workspace token before file resolution.
- If neither an explicit nor workspace-default SVD is available, `cmd_fetch` may auto-resolve exactly one `.dbgoracle/*.svd` candidate for opportunistic live peripheral capture. If discovery is ambiguous or live capture fails, plain `fetch` falls back to non-SVD snapshot capture and emits a clear notice on `stderr`.
- `cmd_fetch` accepts optional `--openocd-tcl-host` and `--openocd-tcl-port` overrides for live peripheral capture. If no explicit or auto-resolved SVD is available, plain `fetch` ignores these overrides and continues with non-SVD capture after emitting a notice.
- When live peripheral capture is in play and no explicit Tcl override is provided, `cmd_fetch` may discover the active OpenOCD Tcl port from the current GDB/MI log and use it for SVD-backed reads.
- If the chosen Tcl endpoint is unreachable, `cmd_fetch` may perform one automatic recovery attempt by discovering the matching live OpenOCD session for the workspace and retrying with its Tcl endpoint.
- Automatic recovery requires a debug session to already be running; `cmd_fetch` must say this explicitly when no live session can be found.
- If an opportunistic auto-discovered SVD still cannot be used after recovery, `cmd_fetch` degrades cleanly to non-SVD snapshot capture and emits a clear notice on `stderr`.
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
- `report --mem [ADDR:SIZE ...]` emits captured memory read entries, or filtered entries matching normalized selectors.
- Combined inspect flags emit one compact JSON object containing only the requested sections plus a top-level `trust` object.
- Inspect payloads that include stream or register sections also include compact snapshot metadata for provenance and freshness.
