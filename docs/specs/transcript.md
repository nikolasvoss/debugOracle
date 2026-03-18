# transcript

- Module: `transcript`
- Code Path: `debugoracle/sources/debuggers/gdb/transcript.py`
- Public Entrypoints: `GDB_TRANSCRIPT_SOURCE`, `GdbTranscriptParseResult`, `parse_gdb_transcript`
- Last Updated: `2026-03-18`

# SPEC: GDB Transcript Source

## Purpose

Parse bounded GDB/MI transcript input as the canonical stream-shaped GDB source.

## Responsibilities

- Expose explicit stream-source metadata for GDB transcript evidence.
- Parse MI records and preserve non-MI context as session events.
- Extract stop, stack, register, and watched-value state from transcript responses.
