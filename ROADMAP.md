# DebugOracle Product Extension Roadmap

This roadmap is ranked by product impact for the current direction:

- agent-driven CLI evidence workflow first
- report-first evidence inspection
- MCP later, after the CLI contract is proven
- probe-backed live reads later
- strict read-only operation
- low-level verification before higher-level features

## Highest impact

1. Stable live debug backend
   Build trustworthy low-level reads first: backend status, register reads, bounded memory reads, and clean error mapping.
2. Agent-usable CLI evidence workflow
   Make `fetch` and `report` the durable same-workspace interface that an agent can drive deterministically before any MCP layer exists.
3. Freshness and provenance model
   Separate captured snapshot data from live reads so stale files never masquerade as current target state.
4. Agent guidance layer
   Suggest the next best evidence request after `report` instead of relying only on free-form prompting.
5. MCP server with snapshot and live tools
   Expose the same proven evidence model through read-only tool calls after the CLI workflow and backend contracts are stable.
6. Safe peripheral read model
   Add allowlisted peripheral reads only after side-effect review and bounded output rules are in place.
7. Serial log ingestion
   Support setups that have no RTT by adding serial as another optional evidence source with the same provenance rules.

## Next expansion wave

8. Session health and observability
   Report probe connectivity, snapshot freshness, parse warnings, and last successful live-read timestamps.
9. Source-context enrichment
   Add source around PC, current function context, and related symbol lookup after raw state access is reliable.
10. Session history and multi-stop timeline
   Preserve more than the latest stop so the agent can reason about sequence and change over time.
11. Interface selector profile
   Add user-controlled interface toggles (RTT, registers, MI, future peripheral sources) so a session can collect or render only relevant streams.
12. Redaction and trust-boundary controls
   Add memory, RTT, and serial scrubbing before wider use on real firmware and customer codebases.
13. Shareable debug bundles
   Package portable evidence bundles for handoff, bug reports, and offline replay.
14. Add better CLI descriptions and examples for human understanding.
15. Add CLI short commands, like -h for --help or -o for --output for more efficient usage.

## Later leverage and UX work

16. VS Code-specific bridge
   Bring the experience closer to an in-editor chat flow after the backend and tool contract are stable.
17. Multi-session and multi-target support
   Handle more advanced probe and workspace setups without breaking the single-session default.
18. Recorded replay and offline investigation mode
   Reuse the same tool surface with saved sessions when hardware is unavailable.
19. Advanced live tools
   Add watch expressions, structured fault-register decoding, and RTOS-aware views after safety and trust are mature.

## Current implementation priority

The current slice focuses only on the low-level-first foundation:

- an agent-usable same-workspace CLI flow
- session and freshness inspection
- managed RTT capture and workspace status
- strict snapshot integrity for user-facing rendering (`report` first, optional `prompt` packaging) with hard-fail on unreadable or malformed snapshot JSON
- `dbgoracle --version` contract with fixed output `0.1.0`
- placeholder source-context cleanup from `future.py` and related placeholder output

Current release framing: **0.1.0**.

The primary near-term operating model is: engineer in chat, agent drives the CLI in the same workspace, human verifies directly when needed.

MCP integration and real hardware adapters are intentionally deferred until the CLI workflow and artifact contracts are stable. The high-level direction for live reads remains: an agent-facing, read-only tool surface for requesting extra target state after snapshot-based evidence is exhausted, rather than public ad hoc CLI commands.
