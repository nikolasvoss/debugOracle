# peripheral_registers

- Module: `peripheral_registers`
- Code Path: `debugoracle/sources/debuggers/gdb/peripheral_registers.py`
- Public Entrypoints: `GDB_PERIPHERAL_REGISTERS_SOURCE`, `SvdDeviceDefinition`, `collect_peripheral_registers_from_svd`, `capture_peripheral_registers_from_svd`, `parse_svd_definition`
- Last Updated: `2026-03-20`

# SPEC: SVD-Backed Peripheral Register Capture

## Purpose

Parse a CMSIS-SVD file, classify safe-readable peripheral registers, and shape live peripheral read results into the canonical snapshot register source.

## Responsibilities

- Expose explicit snapshot-source metadata for SVD-backed peripheral capture.
- Infer device identity from the SVD definition and preserve the resolved SVD file path.
- Build the full SVD-defined peripheral/register catalog for snapshot embedding, including `derivedFrom` peripheral and register inheritance used by real CMSIS-SVD files.
- Capture live peripheral values from the default OpenOCD backend when fetch requests SVD-backed capture.
- Preserve per-register read outcomes using `success`, `failure`, or `skipped`.
- Keep SVD parsing, halt gating, access-policy filtering, and live-read overlay out of CLI and renderer code.

## Capture Contract

- `collect_peripheral_registers_from_svd()` remains the catalog-only builder.
- `capture_peripheral_registers_from_svd()` requires a recent halted stop in the GDB/MI log, and the most recent MI target-state event in the tail window must still be `*stopped`.
- Live capture attempts only registers whose access mode is explicitly safe to read in v1: `read-only` and `read-write`.
- `write-only`, missing access metadata, and unsupported access modes are recorded as `skipped` with a reason.
- Safe-register live reads happen one register at a time through the OpenOCD Tcl control endpoint.
- Successful values are normalized to hex strings before they are stored.
- If zero safe-readable registers exist, or zero register reads succeed, live capture fails clearly.
