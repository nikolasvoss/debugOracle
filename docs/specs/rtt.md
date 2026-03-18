# rtt

- Module: `rtt`
- Code Path: `debugoracle/rtt.py`
- Public Entrypoints: `capture_rtt`, `default_state_path`, `load_capture_state`, `RttCaptureState`, `RttCaptureTimeoutError`, `RTT_STREAM_SOURCE`
- Last Updated: `2026-03-18`

## Purpose

Handle bounded RTT transport capture and state sidecar persistence.

## Responsibilities

- Connect to the OpenOCD RTT TCP endpoint and write stream output to disk.
- Track capture lifecycle state such as waiting, connected, idle, EOF, and errors.
- Persist and reload sidecar state for later session inspection.
- Expose explicit stream-source metadata through `RTT_STREAM_SOURCE`.
- Preserve the old `debugoracle.rtt` import path as a compatibility wrapper.

## Notes

- RTT files and sidecars are transport artifacts, not the final reusable evidence artifact.
- `RTT_STREAM_SOURCE` declares RTT as a passive stream source with no halt requirement.
- The canonical implementation now lives in `debugoracle/sources/streams/rtt.py`.
- `debugoracle/rtt.py` remains only to preserve existing imports and monkeypatch-friendly test surfaces.
