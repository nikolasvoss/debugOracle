# DebugOracle Strategy

## Purpose

This document is the canonical product-story source for DebugOracle.

DebugOracle is a trustworthy, read-only embedded-debug evidence engine. Its job is to collect and shape evidence into reusable artifacts that an engineer and an agent can inspect with confidence.

## Near-Term Operating Model

The primary near-term journey is:

`chat -> agent -> DebugOracle CLI -> grounded answer`

In practice, that means:

1. The engineer asks for help in chat from the same workspace as the debug artifacts.
2. The agent uses deterministic CLI commands such as `fetch` and `report` to gather and inspect evidence.
3. The agent answers from the resulting artifact and asks for more evidence only when the captured evidence is insufficient.
4. The engineer can run the same commands directly for verification, fallback, or deeper inspection.

This is an agent-first operating model, not a different product identity. DebugOracle remains the evidence engine underneath every interface.

## Product Positioning

- Evidence engine first, interface second.
- `report` is the primary agent-facing evidence surface.
- Direct CLI use remains a first-class verification and fallback path.
- MCP is a later interface upgrade, not a dependency for the near-term story.

## What This Strategy Optimizes For

- Trustworthy artifacts with explicit provenance
- Deterministic CLI primitives that agents can invoke repeatedly
- Reusable evidence snapshots that support both human and agent inspection
- Human oversight when evidence is ambiguous or incomplete

## What This Strategy Does Not Mean

- It does not make DebugOracle a chat wrapper.
- It does not promise autonomous debugging in the near term.
- It does not make MCP the gate for agent usability.
- It does not remove the need for a human-verifiable CLI surface.

## Relationship To Other Docs

- [`GOAL.md`](../GOAL.md) defines the product promise and primary user journey.
- [`README.md`](../README.md) explains the supported workflow and onboarding.
- [`ROADMAP.md`](../ROADMAP.md) ranks the next product extensions against this strategy.
- [`architecture.md`](architecture.md) defines the system boundaries and technical invariants.

Deprecated redesign and PoC docs may remain as historical implementation notes, but they are not the canonical source for product direction.
