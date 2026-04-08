# storage

- Module: `storage`
- Code Path: `debugoracle/pipeline/storage.py`
- Public Entrypoints: `build_artifact_from_sources`
- Last Updated: `2026-04-08`

# SPEC: Artifact Storage Assembly

## Purpose

Assemble the canonical investigation artifact from parsed source inputs.

## Responsibilities

- Build top-level summary fields from parsed GDB and RTT evidence.
- Carry through artifact-level metadata such as `schema_version`, `live_state`, `source_context`, and `provenance`.
- Embed full selected source payloads into the snapshot.
- Mark missing unselected sources as absent rather than embedded-empty so inspect modes can fail explicitly.
- Preserve derived convenience structures for later report inspection.

## Snapshot Assembly Contract

`build_artifact_from_sources()` must populate:

- top-level summary fields for stop context, stack, registers, variables, warnings, provenance, and persisted artifact metadata
- `sources.gdb.raw_text` and ordered `sources.gdb.events`
- `sources.rtt.raw_text` and `sources.rtt.lines`
- `sources.registers` for SVD-backed register evidence (embedded or absent)
- `sources.memory` for explicit memory read evidence (embedded or absent)

## Compatibility Notes

- Embedded source sections are canonical for snapshots.
- Raw sidecar export remains transitional and should not be treated as the primary completeness contract.
- Snapshots remain self-contained even when no raw sidecars are exported.
