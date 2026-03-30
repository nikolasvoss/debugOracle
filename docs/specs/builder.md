# builder

- Module: `builder`
- Code Path: `debugoracle/builder.py`
- Public Entrypoints: `build_bundle_from_files`, `build_bundle_from_stream`, `build_bundle_from_text`
- Last Updated: `2026-03-20`

# SPEC: DebugOracle Builder Compatibility Boundary

## Purpose

`debugoracle.builder` still owns bundle construction from raw GDB/MI and RTT inputs.

Builder owns snapshot construction from raw sources and delegates persistence to the canonical artifact repository.

## Canonical Homes

- Raw-evidence parsing and bundle construction stay in `debugoracle/builder.py` for now.
- Canonical artifact models live in `debugoracle/artifacts/models.py`.
- Canonical artifact persistence lives in `debugoracle/artifacts/repository.py`.
- Canonical source-descriptor contract lives in `debugoracle/sources/base.py`.
- Canonical GDB source modules now live under `debugoracle/sources/debuggers/gdb/`.
- Canonical shaping/storage assembly now lives in `debugoracle/pipeline/storage.py`.

## Boundary Contract

Builder exposes construction entrypoints only:

- `from debugoracle.builder import build_bundle_from_files`
- `from debugoracle.builder import build_bundle_from_stream`
- `from debugoracle.builder import build_bundle_from_text`

Artifact persistence must be accessed from `debugoracle.artifacts.repository`.

For Step 6:

- Transcript-style GDB handling now lives in `debugoracle/sources/debuggers/gdb/transcript.py`
- Halt snapshot extraction now lives in `debugoracle/sources/debuggers/gdb/halt_snapshot.py`
- `debugoracle.builder` remains the compatibility-facing orchestrator that assembles artifacts from those canonical GDB modules

For Step 7:

- Artifact creation now happens through `debugoracle.pipeline.storage.build_artifact_from_sources`
- `debugoracle.builder` remains the orchestrator for `build_bundle_from_*` entrypoints.

For Variable Evidence v1:

- Builder assembles snapshots with structured variable evidence under bucketed entries
  (`locals`, `globals`, `watchpoints`, `unknown`).
- `build_bundle_from_*` APIs remain unchanged while returning canonical artifact schema data.

## Snapshot Embedding Contract

- Builder-facing artifact construction must preserve full selected source payloads inside the saved
  snapshot.
- GDB data is stored both as raw transcript text and as the ordered parsed event list derived from
  that transcript.
- RTT data is stored both as raw text and as a convenient line-oriented representation.
- Top-level summary fields remain available for cheap access, but they are derived from the
  embedded source payloads rather than replacing them.
- When `svd_file_path` is provided without an explicit live-capture opt-in, builder embeds the SVD-derived peripheral/register catalog without touching a live backend.
- Builder only attempts live peripheral capture when the caller sets `enable_live_peripheral_capture=True`; this is how `fetch --svd-file <file>` opts into halted OpenOCD-backed reads.
- If live capture is enabled and the transcript does not show a recent stop, or no peripheral values are captured successfully, bundle construction fails instead of silently downgrading to a catalog-only register source.
