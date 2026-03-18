# evidence

- Module: `evidence`
- Code Path: `debugoracle/cli/commands/evidence.py`
- Public Entrypoints: `cmd_observe`, `cmd_snapshot`, `cmd_report`, `cmd_prompt`
- Last Updated: `2026-03-18`

# SPEC: DebugOracle Evidence Commands

## Purpose

Own the CLI flows that resolve raw or saved evidence, build or load artifacts, and render them.

## Responsibilities

- Resolve snapshot, GDB/MI, and RTT inputs for evidence-oriented commands.
- Build investigation artifacts from raw evidence when required.
- Save snapshots for `observe` and render snapshot/report/prompt outputs for reuse.

## Boundaries

- Use artifact persistence, pipeline/builder shaping, and renderer modules rather than reimplementing them here.
- Keep command-specific path resolution and CLI messaging here.
- Do not own parser construction; that belongs in `debugoracle/cli/main.py`.
