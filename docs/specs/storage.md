# storage

- Module: `storage`
- Code Path: `debugoracle/pipeline/storage.py`
- Public Entrypoints: `build_artifact_from_sources`
- Last Updated: `2026-03-20`

# SPEC: Artifact Storage Assembly

## Purpose

Assemble the canonical investigation artifact from parsed source inputs.

## Responsibilities

- Build top-level summary fields from parsed GDB and RTT evidence.
- Embed full selected source payloads into the snapshot.
- Mark missing unselected sources as absent rather than embedded-empty so inspect modes can fail explicitly.
- Preserve derived convenience structures for later report inspection.

## Snapshot Assembly Contract

`build_artifact_from_sources()` must populate:

- top-level summary fields for stop context, stack, registers, variables, warnings, and provenance
- `sources.gdb.raw_text` and ordered `sources.gdb.events`
- `sources.rtt.raw_text` and `sources.rtt.lines`
- legacy top-level `session_events` and `recent_rtt` compatibility fields while migration is in progress

## Compatibility Notes

- Embedded source sections are canonical for new snapshots.
- Legacy top-level stream fields remain available so older report flows can keep working during the redesign.
- Raw sidecar export remains transitional and should not be treated as the primary completeness contract.
- New snapshots remain self-contained even when no raw sidecars are exported.
