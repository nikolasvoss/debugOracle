# DebugOracle Product Extension Roadmap

This roadmap is ranked by product impact for the current direction:

- MCP-capable chat client first
- probe-backed live reads later
- strict read-only operation
- low-level verification before higher-level features

## Highest impact

1. Stable live debug backend
   Build trustworthy low-level reads first: backend status, register reads, bounded memory reads, and clean error mapping.
2. MCP server with snapshot and live tools
   Expose DebugOracle state to a chat agent through read-only tool calls once the low-level backend is proven.
3. Freshness and provenance model
   Separate captured snapshot data from live reads so stale files never masquerade as current target state.
4. Safe peripheral read model
   Add allowlisted peripheral reads only after side-effect review and bounded output rules are in place.
5. Serial log ingestion
   Support setups that have no RTT by adding serial as another optional evidence source with the same provenance rules.

## Next expansion wave

6. Session health and observability
   Report probe connectivity, snapshot freshness, parse warnings, and last successful live-read timestamps.
7. Source-context enrichment
   Add source around PC, current function context, and related symbol lookup after raw state access is reliable.
8. Session history and multi-stop timeline
   Preserve more than the latest stop so the agent can reason about sequence and change over time.
9. Interface selector profile
   Add user-controlled interface toggles (RTT, registers, MI, future peripheral sources) so a session can collect or render only relevant streams.
10. Redaction and trust-boundary controls
   Add memory, RTT, and serial scrubbing before wider use on real firmware and customer codebases.
11. Shareable debug bundles
   Package portable evidence bundles for handoff, bug reports, and offline replay.

## Later leverage and UX work

12. Agent guidance layer
   Suggest the next best evidence request instead of relying only on free-form prompting.
13. VS Code-specific bridge
   Bring the experience closer to an in-editor chat flow after the backend and tool contract are stable.
14. Multi-session and multi-target support
   Handle more advanced probe and workspace setups without breaking the single-session default.
15. Recorded replay and offline investigation mode
    Reuse the same tool surface with saved sessions when hardware is unavailable.
16. Advanced live tools
    Add watch expressions, structured fault-register decoding, and RTOS-aware views after safety and trust are mature.

## Current implementation priority

The current slice focuses only on the low-level-first foundation:

- session and freshness inspection
- a pluggable live backend contract
- a deterministic demo backend
- CLI verification commands
- strict snapshot integrity for user-facing rendering (`report`, `prompt`, `snapshot`) with hard-fail on unreadable or malformed snapshot JSON
- `dbgoracle --version` contract with fixed output `0.1.0`
- placeholder source-context cleanup from `future.py` and related placeholder output

Current release framing: **0.1.0**.

MCP integration and real hardware adapters are intentionally deferred to the next slice.
