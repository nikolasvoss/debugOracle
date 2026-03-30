# DebugOracle Artifact Schema

## Purpose
This document defines the canonical on-disk schema for DebugOracle investigation artifacts.

## Schema Version
Current schema version: `4`

New snapshots written by DebugOracle include:

```json
{
  "schema_version": "4"
}
```

## Load Policy
Artifact loading is strict:
- Missing or invalid JSON payloads fail to load.
- Missing `schema_version` fails to load.
- Unsupported schema versions fail to load.
- Missing canonical `sources` shape (`sources.gdb`, `sources.rtt`, `sources.registers`) fails to load.

Best-effort legacy compatibility is intentionally not supported.

## Required Core Fields
Canonical artifact fields:
- `schema_version`
- `snapshot_id`
- `captured_at`
- `stop_reason`
- `pc`
- `lr`
- `sp`
- `frames`
- `registers`
- `variable_evidence`
- `sources`
- `parse_warnings`
- `provenance`

## Required Embedded Sources
- `sources.gdb.raw_text`
- `sources.gdb.events`
- `sources.gdb.event_count`
- `sources.gdb.embedded`
- `sources.rtt.raw_text`
- `sources.rtt.lines`
- `sources.rtt.line_count`
- `sources.rtt.embedded`
- `sources.registers.embedded`
- `sources.registers.*` register payload (when embedded)

## Optional Fields
- `live_state`
- `source_context`

## Removed Compatibility Fields
These legacy top-level fields are not part of schema v4:
- `recent_rtt`
- `session_events`
- `watched_values`

## Trust Boundary Notes
- Snapshot JSON is untrusted input when loading.
- `provenance` may contain sensitive local paths or raw-export references.
- `live_state` remains distinct from captured evidence.
