# Architecture Refactor Procedure

## Purpose

This document is the implementation procedure for the target architecture defined in [../architecture.md](../architecture.md).

It is not the architecture definition itself. Its job is to describe the execution sequence, safeguards, and verification needed to carry the current flat implementation into the target package structure without requiring the implementer to make new architecture decisions.

## Current State

The current implementation is still mostly flat and centered around a few broad modules:

- `debugoracle/cli.py` owns CLI parsing and a large amount of orchestration logic.
- `debugoracle/builder.py` owns much of the evidence parsing, shaping, and snapshot construction.
- `debugoracle/output.py` owns rendering for report, snapshot, and prompt output.
- `debugoracle/rtt.py` owns RTT capture behavior and transport state handling.
- `debugoracle/live.py` owns the current live backend abstraction and memory read validation.
- `debugoracle/session.py` owns workspace/session resolution and session status rendering.
- `debugoracle/models.py` owns the bundle schema and request/package dataclasses.

This flat structure works for the current product slice, but it hides the intended functional boundaries and will make future source expansion harder to maintain if left as-is.

## Target State

The target package boundaries are:

- `artifacts`
- `policy`
- `sources`
- `pipeline`
- `renderers`
- `cli`

The future structure should make these rules obvious:

- sources are the primary functional entry points
- source families are explicit
- shaping logic lives in the middle pipeline
- rendering stays outside the core
- the persisted unit is an investigation artifact

## Invariants To Preserve

The refactor must preserve the following product and migration invariants:

- halt-centric analysis remains the default model
- the system remains read-only
- requested reads remain canonically persisted for now
- every source implementation must declare explicit source metadata
- public CLI behavior remains compatible during migration
- existing snapshot schema compatibility is preserved

## Procedure

### Step 1: Establish compatibility boundaries before moving logic

Goal:
- Create a migration path so internal code can move without breaking the current CLI entrypoint, tests, or snapshot loading behavior.

Files/modules affected:
- `debugoracle/cli.py`
- `debugoracle/models.py`
- `debugoracle/builder.py`
- import sites in tests

Dependencies/prerequisites:
- [../architecture.md](../architecture.md) is the source of truth for target boundaries.
- Existing CLI and snapshot contracts are identified and treated as temporary compatibility boundaries.

Acceptance criteria:
- A thin compatibility layer can remain at `debugoracle.cli.main`.
- Bundle load/save behavior has a stable compatibility boundary before model moves begin.
- Tests can continue to target old import paths during intermediate steps.

Rollback note if the step fails:
- Do not move any logic yet. Restore focus to documenting stable public and test-facing import boundaries first.

### Step 2: Extract artifact schema and persistence into `artifacts`

Goal:
- Move the canonical persisted unit and snapshot persistence logic into a dedicated artifact boundary.

Files/modules affected:
- logic currently in `debugoracle/models.py`
- logic currently in `debugoracle/builder.py`
- artifact-related tests such as `tests/test_artifact_schema.py`

Dependencies/prerequisites:
- Compatibility boundaries from Step 1 are in place.
- The persisted unit remains conceptually aligned with the investigation artifact defined in the architecture doc.

Acceptance criteria:
- Artifact schema types and load/save behavior live under `debugoracle/artifacts/`.
- Existing snapshot schema version behavior still works in strict and non-strict modes.
- Existing callers can still load and save artifacts without a flag-day rename.

Rollback note if the step fails:
- Restore artifact schema and persistence behavior to the current modules and retry only after compatibility shims are clarified.

### Step 3: Introduce policy modules for halted-analysis and read limits

Goal:
- Centralize product rules around halt requirements, read-only constraints, and bounded reads.

Files/modules affected:
- `debugoracle/live.py`
- `debugoracle/session.py`
- new `debugoracle/policy/` modules

Dependencies/prerequisites:
- Artifact boundary exists so policy code can target stable concepts rather than ad hoc CLI state.

Acceptance criteria:
- Halt-required logic is no longer spread across CLI or backend modules.
- Memory read size limits live in policy, not in command handlers.
- Running-target or unknown-target reads can be explicitly rejected or downgraded by policy.

Rollback note if the step fails:
- Keep current validation where it is and retry with a narrower policy split that covers halted analysis first.

### Step 4: Define the source contract and descriptor metadata

Goal:
- Make source family and collection semantics explicit in code before splitting source implementations across packages.

Files/modules affected:
- new source contract module under `debugoracle/sources/`
- source-producing modules such as `debugoracle/rtt.py`, GDB-related builder logic, and future live read providers

Dependencies/prerequisites:
- Policy concepts exist for `requires_halt` and bounded reads.
- Architecture invariants are already documented and stable.

Acceptance criteria:
- Every implemented source exposes required metadata fields.
- Source family is explicit as `stream` or `snapshot`.
- Collection semantics are inspectable in code and usable in tests.

Rollback note if the step fails:
- Keep the contract draft isolated and do not migrate source implementations until the minimum descriptor shape is stable.

### Step 5: Move RTT into `sources/streams`

Goal:
- Relocate RTT capture into the explicit source layer as a stream source.

Files/modules affected:
- `debugoracle/rtt.py`
- `debugoracle/cli.py`
- relevant RTT tests such as `tests/test_rtt_capture.py` and `tests/test_run_stop.py`

Dependencies/prerequisites:
- Source descriptor contract exists.
- Compatibility imports are available for current RTT call sites.

Acceptance criteria:
- RTT is implemented under `debugoracle/sources/streams/`.
- RTT declares stream-family metadata.
- Current CLI run/capture/stop behavior remains intact.

Rollback note if the step fails:
- Restore RTT imports to the original module and keep the new location unused until command and test wiring are stable.

### Step 6: Split GDB transcript and halt-snapshot logic into `sources/debuggers/gdb`

Goal:
- Separate stream-shaped GDB transcript handling from halt-shaped GDB evidence extraction while keeping one clear GDB home.

Files/modules affected:
- GDB parsing and extraction logic currently in `debugoracle/builder.py`
- MI parsing integration points in `debugoracle/mi.py`
- GDB-related tests such as `tests/test_mi_parse.py`, `tests/test_cli_flow.py`, and `tests/test_cortex_debug_examples.py`

Dependencies/prerequisites:
- Source contract exists.
- RTT source move is complete enough to validate the source layer pattern.

Acceptance criteria:
- Transcript-style handling lives in `sources/debuggers/gdb/transcript.py`.
- Halt snapshot extraction lives in `sources/debuggers/gdb/halt_snapshot.py`.
- GDB-backed registers and memory have a clear home under the same GDB source area.

Rollback note if the step fails:
- Move only transcript parsing first and defer halt-snapshot extraction until the source boundaries are clearer in tests.

### Step 7: Move shaping logic into `pipeline`

Goal:
- Concentrate shared normalization, reduction, provenance, and storage shaping in one middle layer.

Files/modules affected:
- shaping logic currently in `debugoracle/builder.py`
- provenance handling in artifact construction
- any duplicated reduction or normalization logic uncovered during Steps 5 and 6

Dependencies/prerequisites:
- Source inputs now produce stable, typed records or structured intermediate data.
- Artifact boundary exists to receive shaped output.

Acceptance criteria:
- Shared shaping logic lives under `debugoracle/pipeline/`.
- Source modules stop owning reusable shaping behavior.
- Artifact creation happens from pipeline outputs rather than ad hoc direct assembly in CLI paths.

Rollback note if the step fails:
- Revert to the last stable artifact-building path and re-scope the pipeline move into smaller pieces, starting with provenance only.

### Step 8: Move formatting logic into `renderers`

Goal:
- Separate presentation concerns from artifact construction and session state logic.

Files/modules affected:
- `debugoracle/output.py`
- formatting logic in `debugoracle/session.py`
- rendering-related CLI call sites

Dependencies/prerequisites:
- Artifacts and pipeline outputs are stable enough for renderers to consume shaped data instead of raw inputs.

Acceptance criteria:
- Snapshot, report, prompt, and status rendering live under `debugoracle/renderers/`.
- Rendering modules do not take ownership of parsing, shaping, or transport logic.
- Existing output contracts stay unchanged unless a later implementation step intentionally updates them.

Rollback note if the step fails:
- Keep existing renderer imports intact and migrate one renderer surface at a time, starting with report output.

### Step 9: Split CLI orchestration into `cli/main.py` and `cli/commands`

Goal:
- Reduce `debugoracle/cli.py` to a compatibility-facing entrypoint and move command behavior into clearer command modules.

Files/modules affected:
- `debugoracle/cli.py`
- new `debugoracle/cli/main.py`
- new `debugoracle/cli/commands/*`
- CLI-focused tests such as `tests/test_cli_flow.py`, `tests/test_cli_live.py`, and `tests/test_run_stop.py`

Dependencies/prerequisites:
- Source, pipeline, renderer, and policy boundaries are already usable.

Acceptance criteria:
- Command parsing and dispatch are easier to navigate by behavior.
- `debugoracle.cli.main` still works during migration.
- Command modules call core logic rather than embedding product rules.

Rollback note if the step fails:
- Preserve the old single-file CLI and only extract one command family at a time behind the existing entrypoint.

### Step 10: Update module specs and architecture references

Goal:
- Keep maintainer and agent guidance aligned with the new code layout as it changes.

Files/modules affected:
- `docs/specs/README.md`
- per-module spec files under `docs/specs/`
- `docs/architecture.md`
- top-level doc links in `README.md` as needed

Dependencies/prerequisites:
- The code moves for the relevant modules are complete enough that docs can point to stable locations.

Acceptance criteria:
- Module registry entries point to the correct code paths.
- New or moved Python modules have matching specs where required.
- Architecture docs reflect the real implementation boundaries rather than aspirational ones.

Rollback note if the step fails:
- Do not leave stale file paths in the docs. Revert doc references to the last correct paths until code movement is finalized.

### Step 11: Remove temporary compatibility shims only after test coverage passes

Goal:
- Clean up migration scaffolding only when the new package boundaries are proven by tests.

Files/modules affected:
- temporary import shims
- compatibility aliases
- legacy module entrypoints retained during earlier steps

Dependencies/prerequisites:
- Module, behavior, compatibility, and regression verification all pass.
- Module specs and architecture docs already reflect the post-migration structure.

Acceptance criteria:
- Temporary shims are removed only when no longer required by tests or public compatibility policy.
- The new structure is the real structure, not a second layer beneath legacy facades.

Rollback note if the step fails:
- Restore the shims and defer cleanup. Compatibility is preferred over premature neatness.

## Test And Verification Procedure

The following verification work must be documented and executed during implementation, but not in this documentation-only phase.

### Module-level verification

- source module tests for RTT, GDB transcript handling, halt snapshot extraction, and future source descriptors
- pipeline tests for normalization, reduction, provenance, and artifact shaping
- artifact tests for schema versioning, strict/non-strict loading, and persistence behavior
- renderer tests for snapshot, report, prompt, and status output
- policy tests for halted-analysis rules and read limits

### Behavior-level verification

- halted-analysis requirements are enforced consistently
- requested reads remain canonically persisted
- provenance survives artifact construction and reloading
- every implemented source exposes the required source metadata

### Compatibility verification

- legacy snapshot loading still works where compatibility is promised
- `debugoracle.cli.main` remains callable during migration
- existing CLI output contracts continue to match current behavior unless intentionally changed

### Negative-path coverage

- malformed MI input
- unreadable input files
- invalid memory requests
- running-target reads
- unknown schema versions

## Assumptions And Defaults

- This phase is documentation-only.
- No code or package refactor work should be performed as part of creating this document.
- The implementation remains incremental; no flag-day rewrite is required.
- Current public CLI behavior should remain stable unless a later implementation step explicitly changes it.
- If module names or boundaries change during implementation, this procedure document and [../architecture.md](../architecture.md) must be updated together.
