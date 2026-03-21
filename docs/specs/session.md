# session

- Module: `session`
- Code Path: `debugoracle/session.py`
- Public Entrypoints: `SessionConfig`, `collect_session_status`, `render_session_status`
- Last Updated: `2026-03-18`

## Purpose

Resolve workspace artifact locations, report overall session health, and derive the next recommended CLI step.

## Responsibilities

- Resolve default snapshot, MI, RTT, and RTT-state paths from a workspace root.
- Inspect artifact freshness and managed RTT capture status.
- Derive an actionable workspace state plus a deterministic recommended next command.
- Treat corrupt or policy-invalid snapshots as unusable when recommending the next command.
- Apply shared halt-analysis policy to artifact live-state metadata when present.
- Render session health in text or JSON form via `debugoracle/renderers/status.py`.

## Notes

- Session health remains artifact-first; it does not perform live reads itself.
- If a persisted artifact explicitly records a non-halted `target_state`, session health degrades through `debugoracle/policy/halted_analysis.py`.
