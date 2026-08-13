# Claude Code Compatibility Task Spec

Status: Complete

## Problem Statement

DebugOracle's CLI already works independently of the coding agent, but the
repository exposes project instructions only through `AGENTS.md`. Claude Code
loads `CLAUDE.md`, so it does not receive the repository's required workflow
and safety guidance automatically.

## Scope

- In scope:
  - Add a root `CLAUDE.md` that imports the canonical `AGENTS.md` guide.
  - Name Codex and Claude Code in the README's agent-assisted setup guidance.
  - Preserve the existing installation prompts and approval boundaries.
- Out of scope:
  - Claude Code installation, authentication, configuration, or version checks.
  - Claude API, SDK, plugin, or MCP integration.
  - DebugOracle CLI behavior, artifact formats, or platform support changes.

## Invariants Touched

- Read-only: the compatibility path adds no host, workspace, or target mutation.
- Reproducible: both supported agents receive the same canonical repository
  instructions.

## Acceptance Criteria

- AC-001: A Claude Code session opened at repository root receives the canonical
  project instructions through `CLAUDE.md` importing `AGENTS.md`.
- AC-002: README setup guidance explicitly supports Codex and Claude Code while
  retaining the existing explicit-approval boundaries.
- AC-003: A regression test detects removal of either the Claude instruction
  entry point or the named-agent README guidance.

## Risks

- Technical risk: duplicated instruction text could drift between agents.
- Operational risk: users could infer that DebugOracle installs or manages
  Claude Code.

## Rollback Plan

Revert `CLAUDE.md`, its focused regression test, and the README wording. No
runtime state, user configuration, or artifact migration is involved.
