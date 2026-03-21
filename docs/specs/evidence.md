# evidence

- Module: `evidence`
- Code Path: `debugoracle/cli/commands/evidence.py`
- Public Entrypoints: `cmd_fetch`, `cmd_report`, `cmd_prompt`
- Last Updated: `2026-03-20`

# SPEC: DebugOracle Evidence Commands

## Purpose

Own the CLI flows that resolve raw or saved evidence, build or load artifacts, and render them.

## Responsibilities

- Resolve raw evidence for `fetch`.
- Resolve snapshot input for `report` and `prompt`.
- Build investigation artifacts from raw evidence when required.
- Save snapshots for `fetch` and render report/prompt outputs for reuse.
- Keep `fetch` stdout operational by summarizing the saved snapshot rather than rendering interpretive evidence.
- Thread `report` inspect-mode flags into the renderer layer without rebuilding from raw evidence.
- Keep prompt-specific variable selectors isolated from the report parser surface.

## Boundaries

- Use artifact persistence, pipeline/builder shaping, and renderer modules rather than reimplementing them here.
- Keep command-specific path resolution and CLI messaging here.
- Do not own parser construction; that belongs in `debugoracle/cli/main.py`.

## Command Resolution Contract

- `cmd_fetch` is raw-only and never loads a snapshot as its primary evidence source.
- `cmd_fetch --svd-file <file>` is the only CLI path that enables live peripheral capture; it passes an explicit opt-in through the builder instead of relying on `svd_file_path` alone.
- `cmd_fetch` may auto-resolve exactly one `.dbgoracle/*.svd` candidate for opportunistic live peripheral capture. If discovery is ambiguous or live capture fails, plain `fetch` falls back to non-SVD snapshot capture and emits a clear notice on `stderr`.
- `cmd_fetch` accepts optional `--openocd-tcl-host` and `--openocd-tcl-port` overrides for live peripheral capture. If no explicit or auto-resolved SVD is available, plain `fetch` ignores these overrides and continues with non-SVD capture after emitting a notice.
- `cmd_report` is snapshot-only and fails clearly when no snapshot can be resolved.
- `cmd_report` points users to `fetch` when no snapshot is available.
- `cmd_prompt` is snapshot-only and fails clearly when no snapshot can be resolved.
- `cmd_prompt` does not accept stale raw-build tuning flags.
- `cmd_prompt` points users to `fetch` when no snapshot is available.

## Report Inspect Contract

- Default `report` output is a human-readable summary.
- `report --vars [NAME ...]` emits a compact JSON object under `variables`.
- `report --gdb [--tail N]` emits a compact JSON object under `gdb`.
- `report --rtt [--tail N]` emits a compact JSON object under `rtt`.
- `report --verbose [--tail N]` emits a compact JSON object containing summary, variables, source
  streams, and provenance metadata.
- Combined inspect flags emit one compact JSON object containing only the requested sections.
- Inspect payloads that include stream or register sections also include compact snapshot metadata for provenance and freshness.
