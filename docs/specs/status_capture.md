# status_capture

- Module: `status_capture`
- Code Path: `debugoracle/cli/commands/status_capture.py`
- Public Entrypoints: `cmd_status`, `cmd_capture_rtt`
- Last Updated: `2026-03-18`

# SPEC: DebugOracle Session Status And RTT Capture Commands

## Purpose

Hold the transport-health command handlers that do not manage detached runtime lifecycle.

## Responsibilities

- Render workspace/session health via the session model and status renderer.
- Run one-shot RTT capture into a file and state sidecar.
- Translate transport errors into CLI exit codes and user-facing messages.

## Boundaries

- Use session and renderer modules for status behavior.
- Use the canonical RTT stream implementation for capture behavior.
- Do not own detached process management; that belongs in `run_stop.py`.
