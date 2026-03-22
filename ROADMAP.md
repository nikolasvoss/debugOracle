# DebugOracle Product Roadmap

This roadmap tracks product sequencing for the current DebugOracle direction.

The canonical product story lives in [`docs/strategy.md`](docs/strategy.md).
The product promise and primary user journey live in [`GOAL.md`](GOAL.md).
The supported workflow and command contract live in [`README.md`](README.md).

Near-term, DebugOracle is:

- an agent-driven CLI evidence workflow
- `fetch` for capture
- `report` for inspection
- read-only by default
- trust, freshness, and provenance first

## Product guardrails

- Core user question: "Why does my code not do x?"
- DebugOracle should help an agent explain the gap between intended behavior and observed target state.
- Default CLI feedback should answer three things quickly: current state, available evidence, and the next best debugging step.
- New work should strengthen the evidence loop, not just expose more raw debugger detail.

## Now

1. Stable capture and reporting
   Make the `fetch -> report` workflow reliable, deterministic, and easy for an agent or engineer to repeat in the same workspace.
2. Freshness and provenance model
   Keep captured snapshot data, optional live reads, and older artifacts clearly separated so stale evidence never looks current.
3. Session health and observability
   Surface probe connectivity, artifact freshness, parse warnings, and transport health early enough to prevent silent failure.
4. Safe halted live reads
   Support bounded, read-only live enrichment only when the target state is trustworthy and the read path is clearly safe.
5. Clear agent-facing guidance
   Keep command behavior, evidence expectations, and fallback paths obvious so an agent can use the CLI without guessing.

## Next

6. Serial as optional evidence
   Add serial capture as another evidence source for setups where RTT is unavailable, while preserving the same provenance rules.
7. Streamline project setup to maximize setup success rate.
8. Session history and multi-stop timeline
   Preserve more than the latest stop so an agent can reason about sequence, transitions, and change over time.
9. Interface selection and evidence shaping
   Let a session collect or render only the evidence streams that matter without weakening the default path.
10. Redaction and trust-boundary controls
   Add memory, RTT, and serial scrubbing before broader artifact sharing becomes a routine workflow.

## Later

11. Shareable debug bundles
   Package portable evidence bundles for handoff, bug reports, and offline reuse once trust-boundary controls are in place.
12. VS Code-specific workflow improvements
   Reduce setup friction and make the in-editor path smoother after the CLI workflow is boringly reliable.
13. Multi-session and multi-target support
   Expand beyond the single-session default without making the common case harder to understand or operate.
14. Recorded replay and offline investigation
   Reuse the same evidence surfaces with saved sessions when hardware is unavailable.
15. Advanced live views
   Add higher-level live inspection such as watch expressions, structured fault decoding, and RTOS-aware views after safety and trust are mature.

## Current milestone

The current milestone is a trustworthy low-level foundation for agent-assisted CLI debugging:

- a same-workspace `fetch -> report` flow that is easy to verify directly
- explicit session status, freshness, and trust reporting
- managed RTT capture and workspace health checks
- strict snapshot integrity for user-facing rendering
- optional halted peripheral enrichment that stays read-only and bounded

The operating model remains: engineer in chat, agent drives deterministic CLI commands in the same workspace, and the engineer verifies directly when needed.
