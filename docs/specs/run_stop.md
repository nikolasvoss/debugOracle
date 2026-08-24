# run_stop

- Module: `run_stop`
- Code Path: `debugoracle/cli/commands/run_stop.py`
- Public Entrypoints: `cmd_run`, `cmd_stop`
- Last Updated: `2026-08-24`

# SPEC: DebugOracle Managed RTT Run Commands

## Purpose

Own the workspace-oriented RTT lifecycle commands used for foreground and detached capture flows.

## Responsibilities

- Resolve managed RTT output, state, runtime metadata, and launch-log paths.
- Start detached RTT capture processes and persist runtime metadata.
- Stop only managed DebugOracle run processes and clean stale metadata safely.
- Bind stop signals to the exact Linux process instance through `pidfd`; open
  the handle before validating `/proc` start time, executable, exact argv, and
  canonical workspace identity, and revalidate before force escalation.
- Stop a newly launched detached child if safe runtime metadata cannot be
  published; never leave an unmanaged child after an atomic-write failure.
- Ensure detached RTT child launches can still import `debugoracle` when run
  from an external workspace without an editable install.

## Boundaries

- Delegate actual RTT stream capture to the canonical RTT source implementation.
- Keep process ownership checks and runtime metadata handling here.
- Fail closed without signaling when Linux `pidfd` or required `/proc` identity
  evidence is unavailable.
- Avoid owning snapshot building, rendering, or session-health rendering.
