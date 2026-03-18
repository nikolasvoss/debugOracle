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
- Raise clear parser errors for malformed MI fragments.

## Notes

- This module should stay small and deterministic because higher-level evidence building depends on it heavily.
