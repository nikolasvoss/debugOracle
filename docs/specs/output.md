# output

- Module: `output`
- Code Path: `debugoracle/output.py`
- Public Entrypoints: `build_prompt_package`, `render_prompt`, `render_report`, `render_snapshot`
- Last Updated: `2026-03-18`

## Purpose

Render structured evidence into human-facing reports, snapshots, and agent-ready prompt packages.

## Responsibilities

- Build a prompt package from evidence plus an investigation request.
- Render prompt, report, and snapshot views in markdown, text, or JSON as applicable.
- Summarize parsing quality, warnings, stack state, and recent RTT evidence.

## Notes

- This module should not mutate evidence; it formats already-built structures.
