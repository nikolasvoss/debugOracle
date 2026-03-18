# mi

- Module: `mi`
- Code Path: `debugoracle/mi.py`
- Public Entrypoints: `parse_mi_record`, `MIParseError`, `MIRecord`
- Last Updated: `2026-03-18`

## Purpose

Parse individual GDB/MI records into structured Python data.

## Responsibilities

- Identify supported MI record prefixes.
- Parse tuples, lists, strings, and repeated keys from MI payloads.
- Stay as the small parser boundary used by `debugoracle/sources/debuggers/gdb/transcript.py`.

## Notes

- This module remains parser-focused; transcript classification and halt-snapshot extraction now live under the GDB source area.
