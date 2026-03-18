# live

- Module: `live`
- Code Path: `debugoracle/live.py`
- Public Entrypoints: `build_live_backend`, `available_backends`, `validate_memory_request`, `render_live_status`, `render_register_result`, `render_memory_result`
- Last Updated: `2026-03-18`

## Purpose

Define the read-only live backend contract and deterministic demo backend used for verification work.

## Responsibilities

- Represent live status, register reads, and memory reads as typed results.
- Validate bounded memory read requests.
- Render live backend results for human-facing CLI output.

## Notes

- The demo backend remains useful for local verification even when live commands are not part of the main CLI workflow.
