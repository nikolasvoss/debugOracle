# DebugOracle Goal

## Product Vision
DebugOracle is a trustworthy embedded-debug evidence engine that helps engineers and their agents turn fragmented debug evidence and safe live state into grounded investigation artifacts.

## Product Direction
Near term, DebugOracle should support one primary operating model: the engineer works from chat, the agent drives deterministic DebugOracle CLI commands in the same workspace, and the human verifies directly when needed.

Long term, it may expose richer agent-facing interfaces such as MCP, but the near-term product does not depend on that upgrade.

## Primary User Journey

1. An engineer asks for debugging help in chat.
2. The agent runs DebugOracle commands such as `fetch` and `report` in the workspace.
3. DebugOracle returns a reusable evidence artifact plus grounded inspection output.
4. The agent answers from that evidence and asks for more evidence when the artifact is insufficient.
5. The engineer can run the same CLI commands directly for verification, fallback, or deeper inspection.

## Target User
Embedded developers working with AI agents and low-level debug workflows, including GDB, runtime traces, registers, logs, and read-only target state.

## Core Problem
Debug evidence is fragmented across logs, runtime streams, registers, and current target state. Moving from that raw evidence to a coherent debugging picture is slow, manual, and error-prone. Engineers need trustworthy structure, provenance, and safe live insight before higher-level debugging guidance can be dependable.

## Product Promise
Reduce time from raw debug evidence to an evidence-backed debugging direction from hours to minutes through agent-mediated investigation with human oversight.

## Constraints
- CLI-first
- Read-only by default
- Deterministic and reproducible where possible
- Compatible with existing debug setups
- Human-verifiable at every step

## Non-Goals
- Full autonomous debugging in the near term
- Automatic bug fixing
- IDE replacement
- Universal platform support in v1
- MCP as a near-term dependency for the core workflow
