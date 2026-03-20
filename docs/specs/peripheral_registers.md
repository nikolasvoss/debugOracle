# peripheral_registers

- Module: `peripheral_registers`
- Code Path: `debugoracle/sources/debuggers/gdb/peripheral_registers.py`
- Public Entrypoints: `GDB_PERIPHERAL_REGISTERS_SOURCE`, `SvdDeviceDefinition`, `collect_peripheral_registers_from_svd`, `parse_svd_definition`
- Last Updated: `2026-03-20`

# SPEC: GDB SVD-Backed Peripheral Register Source

## Purpose

Parse a CMSIS-SVD file and shape the device peripheral/register catalog into the canonical snapshot-embedded register source.

## Responsibilities

- Expose explicit snapshot-source metadata for SVD-backed peripheral register capture.
- Infer device identity from the SVD definition.
- Build the full SVD-defined peripheral/register catalog for snapshot embedding.
- Preserve per-register read outcomes using `success`, `failure`, or `skipped`.
- Keep SVD parsing and register-catalog shaping out of CLI and renderer code.
