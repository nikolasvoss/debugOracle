# halt_snapshot

- Module: `halt_snapshot`
- Code Path: `debugoracle/sources/debuggers/gdb/halt_snapshot.py`
- Public Entrypoints: `GDB_HALT_SNAPSHOT_SOURCE`, `GdbHaltSnapshot`, `build_halt_snapshot`
- Last Updated: `2026-03-18`

# SPEC: GDB Halt Snapshot Source

## Purpose

Shape halt-scoped GDB evidence into the canonical snapshot-oriented halt snapshot record.

## Responsibilities

- Expose explicit snapshot-source metadata for halt-derived GDB evidence.
- Build a compact halt snapshot from parsed stop, stack, register, and watched-value state.
- Keep halt-centric evidence shaping separate from transcript parsing.
