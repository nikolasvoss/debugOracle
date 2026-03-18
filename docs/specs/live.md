# live

- Module: `live`
- Code Path: `debugoracle/live.py`
- Public Entrypoints: `build_live_backend`, `available_backends`, `validate_memory_request`, `render_live_status`, `render_register_result`, `render_memory_result`
- Last Updated: `2026-03-18`

## Purpose

Define the read-only live backend contract and deterministic demo backend used for verification work.

## Responsibilities

- Represent live status, register reads, and memory reads as typed results.
- Delegate halt-required read policy to `debugoracle/policy/halted_analysis.py`.
- Delegate bounded memory read validation to `debugoracle/policy/limits.py`.
- Route canonical GDB-backed register and memory shaping through `debugoracle/sources/debuggers/gdb/registers.py` and `debugoracle/sources/debuggers/gdb/memory.py`.
- Render live backend results for human-facing CLI output.

## Notes

- Running, unknown, or unavailable target states are not treated as safe for correlated live reads.
- `validate_memory_request` remains the compatibility-facing wrapper while the canonical limit rule now lives in policy.
