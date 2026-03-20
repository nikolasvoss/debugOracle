# models

- Module: `models`
- Code Path: `debugoracle/artifacts/models.py`
- Public Entrypoints: `InvestigationArtifact`, `ArtifactSources`, `GdbSource`, `RttSource`, `VariableEvidence`, `VariableEntry`
- Last Updated: `2026-03-20`

# SPEC: Artifact Models

## Purpose

Define the canonical snapshot schema for DebugOracle artifacts.

## Responsibilities

- Preserve cheap top-level summary fields for report and prompt flows.
- Store embedded source payloads under a top-level `sources` object.
- Support best-effort loading of older snapshots that still use legacy top-level stream fields.

## Snapshot Schema Contract

Top-level summary fields remain available for direct access:

- `snapshot_id`
- `captured_at`
- `stop_reason`
- `pc`, `lr`, `sp`
- `frames`
- `registers`
- `variable_evidence`
- `parse_warnings`
- `provenance`

Embedded source fields live under `sources`:

- `sources.gdb.raw_text`
- `sources.gdb.events`
- `sources.gdb.event_count`
- `sources.rtt.raw_text`
- `sources.rtt.lines`
- `sources.rtt.line_count`

## Compatibility Contract

- New snapshots mark embedded source sections explicitly.
- Older snapshots may still load from `session_events` and `recent_rtt`.
- Legacy snapshots must not claim to have embedded source payloads when those sections were not stored.
- GDB event order and variable entry order must remain stable through save/load.
