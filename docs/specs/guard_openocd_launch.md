# guard_openocd_launch

- Module: `guard_openocd_launch`
- Code Path: `debugoracle/cli/commands/guard_openocd_launch.py`
- Public Entrypoints: `cmd_guard_openocd_launch`
- Last Updated: `2026-03-25`

# SPEC: Attach Launch Conflict Guard

## Purpose

Fail generated attach-mode launches early when a workspace-matching OpenOCD process is already active.

## Responsibilities

- Resolve the workspace root for the current launch preflight.
- Fail early when the workspace has not finished DebugOracle setup yet.
- Reuse shared OpenOCD process discovery and workspace matching from `debugoracle/openocd.py`.
- Return success when no workspace-matching OpenOCD process is active.
- Return a clear blocking error when one matching process is active.
- Return a clear blocking error when multiple matching processes make ownership ambiguous.
- Return a clear blocking error when only degraded `ps`-level process data is available and ownership cannot be determined safely.

## Boundaries

- Do not start OpenOCD.
- Do not stop or kill OpenOCD.
- Do not require explicit Tcl-port discovery; manual `make debug` sessions still count as conflicts.
- Use the same workspace-readiness contract as `dbgoracle status` before evaluating process ownership.
- Keep the surface narrow and task-oriented so generated VS Code tasks can call it directly.
