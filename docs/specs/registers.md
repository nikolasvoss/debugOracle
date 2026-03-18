# registers

- Module: `registers`
- Code Path: `debugoracle/sources/debuggers/gdb/registers.py`
- Public Entrypoints: `GDB_REGISTERS_SOURCE`, `collect_gdb_registers`
- Last Updated: `2026-03-18`

# SPEC: GDB Register Source

## Purpose

Provide the canonical source metadata and normalized handoff point for GDB-backed register snapshots.

## Responsibilities

- Expose explicit snapshot-source metadata for halted register reads.
- Keep the register-source home under `debugoracle/sources/debuggers/gdb/`.
- Return a stable register mapping for callers such as live backend adapters.
