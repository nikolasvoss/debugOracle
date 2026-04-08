# memory

- Module: `memory`
- Code Path: `debugoracle/sources/debuggers/gdb/memory.py`
- Public Entrypoints: `GDB_MEMORY_SOURCE`, `GdbMemorySnapshot`, `collect_gdb_memory_read`
- Last Updated: `2026-04-08`

# SPEC: GDB Memory Source

## Purpose

Provide the canonical source metadata and normalized handoff point for GDB-backed memory snapshots.

## Responsibilities

- Expose explicit snapshot-source metadata for halted memory reads.
- Keep the memory-source home under `debugoracle/sources/debuggers/gdb/`.
- Return a compact snapshot record with resolved address, size, and hex payload.
- Parse and normalize `ADDR:SIZE` selectors with bounded size validation.
- Capture deterministic read-only memory entries with explicit success/failure outcomes.
