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
- Store embedded source payloads under a top-level `sources` object.
- Parse canonical snapshots only.

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
- Snapshots without canonical `sources` payloads are rejected during load.
- Unsupported schema versions are rejected during load.
- GDB event order and variable entry order must remain stable through save/load.
