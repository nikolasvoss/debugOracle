# builder

- Module: `builder`
- Code Path: `debugoracle/builder.py`
- Public Entrypoints: `build_bundle_from_files`, `build_bundle_from_stream`, `build_bundle_from_text`, `load_bundle`, `save_bundle`
- Last Updated: `2026-03-18`

## Purpose

Build and persist stable evidence bundles from bounded GDB/MI and optional RTT inputs.

## Responsibilities

- Parse raw GDB/MI records into structured stop-context data.
- Normalize frames, registers, watched values, and recent RTT lines.
- Record provenance, parse warnings, and raw-export metadata.
- Load and save bundle JSON with schema compatibility checks.

## Notes

- This module is the primary translation boundary from untrusted text logs into structured evidence.
