# transcript

- Module: `transcript`
- Code Path: `debugoracle/sources/debuggers/gdb/transcript.py`
- Public Entrypoints: `GDB_TRANSCRIPT_SOURCE`, `GdbTranscriptParseResult`, `parse_gdb_transcript`
- Last Updated: `2026-03-20`

# SPEC: GDB Transcript Source

## Purpose

Parse bounded GDB/MI transcript input as the canonical stream-shaped GDB source.

## Responsibilities

- Expose explicit stream-source metadata for GDB transcript evidence.
- Parse MI records and preserve non-MI context as session events.
- Extract stop, stack, register, and structured variable-evidence state from transcript responses.
- Preserve the full raw transcript text so snapshots can embed it alongside parsed events.

## Variable Evidence Notes

- Transcript parsing now preserves variable-like evidence as structured entries rather than a flat
  watched-value map.
- `locals` result records are treated as `locals`.
- Generic `variables` result records default to `unknown` until stronger classification is
  available.
- Watchpoint entries are best-effort and should only be classified as `watchpoints` when the stop
  record exposes clear watchpoint metadata; otherwise they remain in `unknown` at later shaping
  stages.

## Snapshot Embedding Contract

- New snapshots embed the full raw GDB transcript text.
- New snapshots also embed the ordered parsed GDB event stream derived from that raw transcript.
- Stored event order must remain identical to transcript order.
