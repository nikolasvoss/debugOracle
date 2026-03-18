# DebugOracle Artifact Schema

## Purpose
This document defines the current internal schema contract for DebugOracle investigation artifacts.

It exists to keep snapshot JSON stable enough for contributors, tests, and near-term product evolution. It is not a public compatibility promise.

## Non-Goals
- Defining a final long-term artifact model
- Locking the product into a mandatory timeline engine or fixed correlation model
- Replacing tolerant loading with rigid validation everywhere
- Turning the artifact into a public standard for external integrations

## Schema Version
Current schema version: `1`

New snapshots written by DebugOracle should include:

```json
{
  "schema_version": "1"
}
```

Snapshots without `schema_version` are treated as legacy artifacts and normalized to schema version `1` in memory.

Unknown future schema versions:
- warn in non-strict load mode
- fail in strict load mode

## Required Core Fields
The current additive schema keeps the existing top-level bundle shape intact. These fields remain the canonical core of the investigation artifact:

- `schema_version`
- `snapshot_id`
- `captured_at`
- `stop_reason`
- `pc`
- `lr`
- `sp`
- `frames`
- `registers`
- `watched_values`
- `recent_rtt`
- `parse_warnings`
- `provenance`
- `session_events`

## Optional Fields
- `live_state`
- `source_context`

Optional fields may be absent in legacy or partial artifacts.

## Captured Evidence vs Live State
Captured evidence remains in the existing top-level fields such as `frames`, `registers`, `recent_rtt`, and `session_events`.

Live read-only evidence belongs only in `live_state`.

The reserved `live_state` structure is intentionally light and may contain:
- `captured_at`
- `source`
- `backend`
- `status`
- `registers`
- `memory_reads`
- `warnings`

No fixed nested payload contract is required yet beyond `live_state` being a JSON object.

## Flexible Metadata
`provenance` remains a flexible metadata bucket for source paths, counts, quality signals, raw-export metadata, and other supporting fields that are still evolving.

## Compatibility Policy
- Backward compatibility with existing snapshot JSON is preferred over schema purity.
- New additive fields are allowed when they do not rename or remove the current core fields.
- Existing fields should not be moved into new nested structures in this schema version.

## Trust Boundary Notes
- Snapshot JSON must be treated as untrusted input when loading.
- `provenance` may contain sensitive local paths or raw-export references.
- `live_state` must stay distinct from captured evidence so current target state does not get confused with saved artifact state.
