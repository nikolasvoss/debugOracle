# run_stop

- Module: `run_stop`
- Code Path: `debugoracle/cli/commands/run_stop.py`
- Public Entrypoints: `cmd_run`, `cmd_stop`
- Last Updated: `2026-03-18`

# SPEC: DebugOracle Managed RTT Run Commands

## Purpose

Own the workspace-oriented RTT lifecycle commands used for foreground and detached capture flows.

## Responsibilities

- Resolve managed RTT output, state, runtime metadata, and launch-log paths.
- Start detached RTT capture processes and persist runtime metadata.
- Stop only managed DebugOracle run processes and clean stale metadata safely.
- Ensure detached RTT child launches can still import `debugoracle` when run
  from an external workspace without an editable install.

## Boundaries

- Delegate actual RTT stream capture to the canonical RTT source implementation.
- Keep process ownership checks and runtime metadata handling here.
- Avoid owning snapshot building, rendering, or session-health rendering.
