# rtt

- Module: `rtt`
- Code Path: `debugoracle/rtt.py`
- Public Entrypoints: `capture_rtt`, `default_state_path`, `load_capture_state`, `RttCaptureState`, `RttCaptureTimeoutError`
- Last Updated: `2026-03-18`

## Purpose

Handle bounded RTT transport capture and state sidecar persistence.

## Responsibilities

- Connect to the OpenOCD RTT TCP endpoint and write stream output to disk.
- Track capture lifecycle state such as waiting, connected, idle, EOF, and errors.
- Persist and reload sidecar state for later session inspection.

## Notes

- RTT files and sidecars are transport artifacts, not the final reusable evidence bundle.
