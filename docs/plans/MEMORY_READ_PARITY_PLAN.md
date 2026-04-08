# Memory Read Parity Plan (Fetch + Report)

## Summary

Add memory read with same product shape as register read:

- capture intent on `fetch`
- persist canonical evidence in snapshot
- inspect stored values on `report`

This plan uses canonical schema extension, not ad-hoc metadata.

## Scope

### In Scope

- `fetch --mem ADDR:SIZE` (repeatable) for explicit memory capture requests.
- `report --mem [ADDR:SIZE ...]` inspect surface.
- Snapshot schema v5 with canonical `sources.memory`.
- Renderer and metadata updates so memory presence is visible and queryable.
- Tests for parser, fetch/report behavior, schema contracts, and regressions.

### Out of Scope

- New live public CLI commands.
- Auto-discovered/default memory ranges.
- Symbolic memory selectors (v1 is `ADDR:SIZE` only).

## Public CLI Contract

### Fetch

- New flag: `--mem ADDR:SIZE` (repeatable).
- Address must parse as integer (`0x...` or decimal).
- Size must be positive and within bounded memory-read policy limit (`256` bytes max per selector).
- If zero requested ranges succeed: fetch fails clearly.
- If at least one range succeeds: fetch succeeds and records per-range failures.
- Address display in persisted entries preserves user-provided format.

### Report

- New flag: `--mem [ADDR:SIZE ...]`.
- No selectors: return all captured memory entries.
- With selectors: return exact matching captured ranges only, using normalized `(address_int, size)` matching semantics.
- No matches: fail clearly with actionable message.

## Architecture Changes

### 1) Artifact Model

- Add `MemoryReadEntry` and `MemorySource` to `debugoracle/artifacts/models.py`.
- Add `sources.memory` to `ArtifactSources`.
- Add memory presence helpers analogous to register source checks.

### 2) Schema and Loading

- Bump `CURRENT_BUNDLE_SCHEMA_VERSION` from `4` to `5`.
- Loader remains strict: only supported versions load.
- No backward-compatibility requirement for older snapshot schemas.

### 3) Fetch Pipeline

- Thread requested memory selectors from CLI into evidence command and builder/pipeline.
- Use read-only OpenOCD memory-read path with robust bounded chunking:
  - issue `read_memory` in byte-width mode (`width_bits=8`) for deterministic byte payloads
  - split requests into `32`-byte chunks and concatenate in-order
- Preserve deterministic per-range outcomes:
  - `success`: includes captured hex payload.
  - `failure`: includes failure reason.
- Persist aggregate provenance counters (requested/success/failure).
- On zero-success fetch, persist failure entries and counters, then exit failure.

### 4) Report Rendering

- Extend `ReportRenderOptions` with memory inspect selectors.
- Add memory inspect payload section in `debugoracle/renderers/report.py`.
- Include memory availability in metadata/source availability outputs.
- Memory inspect entries expose: `status`, `address`, `size`, `data_hex`, `failure_reason`, `ascii_preview`.
- Deterministic ordering: sort by normalized address ascending, then size ascending.
- Keep default report concise and backward-consistent in style.

## Error and Rescue Rules

- Selector parse/validation errors: fail fast with explicit reason.
- OpenOCD/read failures: recorded per range.
- Fetch exit behavior:
  - `>=1 success` -> success exit.
  - `0 success` -> failure exit (after persisting failure entries).
- Report selector miss: failure with requested selector echo.

## Security and Safety

- Risk tier: medium.
- No target mutation introduced (read-only path only).
- Bound read size using policy limits.
- Explicit user opt-in ranges only (no hidden reads).
- No additional secrets/auth surface added.

## Test Plan

### Parser and Validation

- Accept single and multiple valid `ADDR:SIZE`.
- Reject malformed selectors and out-of-bound sizes.
- Selector matching normalizes to `(address_int, size)`; stored display address preserves input text.

### Fetch Integration

- All-success path stores all requested ranges.
- Partial-success path stores mixed statuses and succeeds.
- Zero-success path stores failure entries, then fails with clear message.

### Report Integration

- `report --mem` returns all captured memory entries.
- Filtered selector queries return subset.
- Missing selector matches fail clearly.

### Schema and Repository

- Snapshot save/load works for schema v5 with `sources.memory`.
- Missing schema still fails.
- v4 snapshot load fails with clear re-fetch guidance.

### Regression

- Verify no regressions in existing:
  - register inspect modes
  - gdb/rtt/vars inspect modes
  - default text report flow

## Validation

Run:

```bash
pre-commit run --all-files
```

## Implementation Targets

- `debugoracle/cli/main.py`
- `debugoracle/cli/commands/evidence.py`
- `debugoracle/artifacts/models.py`
- `debugoracle/artifacts/repository.py`
- `debugoracle/pipeline/storage.py`
- `debugoracle/renderers/report.py`
- memory/read helpers under `debugoracle/sources/debuggers/gdb/` as needed
- specs/docs and focused tests
