# session

- Module: `session`
- Code Path: `debugoracle/session.py`
- Public Entrypoints: `SessionConfig`, `collect_session_status`, `render_session_status`
- Last Updated: `2026-03-18`

## Purpose

Resolve workspace artifact locations and report overall session health.

## Responsibilities

- Resolve default snapshot, MI, RTT, and RTT-state paths from a workspace root.
- Inspect artifact freshness and managed RTT capture status.
- Render session health in text or JSON form.

## Notes

- This module owns workspace-level artifact discovery rules used by the CLI.
