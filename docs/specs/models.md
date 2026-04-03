# models

- Module: `models`
- Code Path: `debugoracle/artifacts/models.py`
- Public Entrypoints: `InvestigationArtifact`, `ArtifactSources`, `GdbSource`, `RttSource`, `RegisterSource`, `VariableEvidence`, `VariableEntry`
- Last Updated: `2026-03-22`

# SPEC: Artifact Models

## Purpose

Define the canonical snapshot schema for DebugOracle artifacts.

## Responsibilities

- Preserve cheap top-level summary fields for report and status flows.
- Preserve artifact-level metadata that is carried through save/load, including schema version and live-state context.
- Store embedded source payloads under a top-level `sources` object.
- Parse canonical snapshots only.

## Snapshot Schema Contract

Top-level summary fields remain available for direct access:

- `schema_version`
- `snapshot_id`
- `captured_at`
- `stop_reason`
- `pc`, `lr`, `sp`
- `frames`
- `registers`
- `variable_evidence`
- `parse_warnings`
- `live_state`
- `source_context`
- `provenance`

Embedded source fields live under `sources`:

- `sources.gdb.raw_text`
- `sources.gdb.events`
- `sources.gdb.event_count`
- `sources.rtt.raw_text`
- `sources.rtt.lines`
- `sources.rtt.line_count`

## Compatibility Contract

- Current schema version: `4`
- New snapshots mark embedded source sections explicitly.
- Snapshots without canonical `sources` payloads are rejected during load.
- Unsupported schema versions are rejected during load.
- GDB event order and variable entry order must remain stable through save/load.
- Legacy top-level fields removed from schema v4 are not part of the canonical contract:
  - `recent_rtt`
  - `session_events`
  - `watched_values`
