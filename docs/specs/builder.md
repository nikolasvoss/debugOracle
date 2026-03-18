# builder

- Module: `builder`
- Code Path: `debugoracle/builder.py`
- Public Entrypoints: `build_bundle_from_files`, `build_bundle_from_stream`, `build_bundle_from_text`, `load_bundle`, `save_bundle`, `SnapshotLoadError`
- Last Updated: `2026-03-18`

# SPEC: DebugOracle Builder Compatibility Boundary

## Purpose

`debugoracle.builder` still owns bundle construction from raw GDB/MI and RTT inputs.

In Step 1 of the architecture refactor it no longer owns snapshot persistence as the canonical
implementation. Instead, it preserves the existing test-facing import surface while delegating
load/save behavior to the new artifact boundary.

## Canonical Homes

- Raw-evidence parsing and bundle construction stay in `debugoracle/builder.py` for now.
- Canonical artifact models live in `debugoracle/artifacts/models.py`.
- Canonical artifact persistence lives in `debugoracle/artifacts/repository.py`.
- `debugoracle/artifacts/bundle.py` remains the bundle-named compatibility shim.
- Canonical source-descriptor contract lives in `debugoracle/sources/base.py`.
- Canonical GDB source modules now live under `debugoracle/sources/debuggers/gdb/`.
- Canonical shaping/storage assembly now lives in `debugoracle/pipeline/storage.py`.

## Compatibility Contract

The following builder imports must continue to work during migration:

- `from debugoracle.builder import build_bundle_from_files`
- `from debugoracle.builder import build_bundle_from_stream`
- `from debugoracle.builder import build_bundle_from_text`
- `from debugoracle.builder import load_bundle`
- `from debugoracle.builder import save_bundle`
- `from debugoracle.builder import SnapshotLoadError`

For Step 2:

- `load_bundle`, `save_bundle`, and `SnapshotLoadError` are compatibility exports backed by
  `debugoracle.artifacts.bundle`, which delegates to `debugoracle.artifacts.repository`
- `build_bundle_from_*` remains implemented locally
- callers and tests are allowed to stay on the old builder import path

For Step 4:

- `debugoracle.builder` exposes explicit source descriptors for the current GDB-derived sources:
  `GDB_TRANSCRIPT_SOURCE` and `GDB_HALT_SNAPSHOT_SOURCE`
- These descriptors declare stream vs snapshot semantics before the later source-package split
- The descriptors are metadata only in this step; they do not yet move GDB code into `debugoracle/sources/`

For Step 6:

- Transcript-style GDB handling now lives in `debugoracle/sources/debuggers/gdb/transcript.py`
- Halt snapshot extraction now lives in `debugoracle/sources/debuggers/gdb/halt_snapshot.py`
- `debugoracle.builder` remains the compatibility-facing orchestrator that assembles artifacts from those canonical GDB modules

For Step 7:

- Artifact creation now happens through `debugoracle.pipeline.storage.build_artifact_from_sources`
- `debugoracle.builder` still owns the legacy `build_bundle_from_*` entrypoints, but it no longer owns the shared shaping logic directly

## Migration Note

Do not move bundle-building or shaping logic out of `debugoracle.builder` as part of this step.
That work belongs to later architecture steps after the persistence boundary is stabilized.
