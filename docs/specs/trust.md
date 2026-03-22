# trust

- Module: `trust`
- Code Path: `debugoracle/policy/trust.py`
- Public Entrypoints: `TrustDecision`, `evaluate_artifact_trust`
- Last Updated: `2026-03-22`

## Purpose

Derive one canonical artifact trust verdict that both session status and report rendering can reuse.

## Responsibilities

- Map snapshot usability, freshness, halt-safety, and parser warnings into `safe`, `caution`, or `unsafe`.
- Produce deterministic reason strings and a recommended next command.
- Keep trust evaluation separate from rendering so CLI surfaces stay aligned.

## Boundaries

- Do not resolve workspace paths or file timestamps; callers provide those facts.
- Do not format text or JSON output; renderers consume the decision.
- Do not mutate artifacts or infer unsupported guarantees from incomplete evidence.
