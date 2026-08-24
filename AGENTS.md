# DebugOracle — Agent Guide

## Purpose

DebugOracle is a **passive embedded debugging evidence system**.

It:
- ingests raw debug data (GDB MI, RTT, memory, registers, docs)
- structures deterministic evidence artifacts
- exposes them for humans and AI agents

**Core idea:**
> Turn a live debug session into a reproducible, queryable evidence set.

---

## Core Invariants (Do Not Break)

1. **Deterministic** — same inputs → same outputs  
2. **Evidence-first** — no inferred state, only traceable data  
3. **Read-only** — no mutation of target system  
4. **Reproducible** — artifacts enable offline reconstruction  
5. **Explicit provenance** — every value has a source  

---

## System Model

Pipeline:

1. Acquire  
2. Normalize  
3. Reduce  
4. Persist  
5. Render  

This model must not change.

---

## Workflow

For any task:

1. Read relevant spec (`docs/specs/`)  
2. Read minimal implementation  
3. Read nearest test  
4. Make smallest correct change  
5. Validate  
6. Expand scope only if required  

### Spec And Branch Protocol (Mandatory)

- New feature or behavior change must follow `docs/workflows/AGENT_WORKFLOW_RULES.md`.
- Public behavior change without a task spec is not allowed.

---

## Validation (Mandatory)

For quick local/agent preflight:

```bash
./scripts/verify.sh fast
```

- `fast` is the default mode when no argument is passed.
- `fast` runs `SKIP=coverage,pytest-fast pre-commit run --all-files`
  (coverage and the full test-suite hook are skipped).

For required final validation before completion:

```bash
./scripts/verify.sh full
```

- `full` runs `pre-commit run --all-files` with no skipped hooks.

Run:

```bash
pre-commit run --all-files
```
This is the **single source of truth for validation**.

- Defined in `.pre-commit-config.yaml` and `pyproject.toml`
- `verify.sh` always excludes HIL tests in both `fast` and `full` modes

### Rules

- Do not claim completion if checks fail
- Do not bypass or weaken checks
- Fix root causes, not symptoms

### Release Artifact Note

- `scripts/verify-release.sh` checks reproducible wheels on every run. It
  compares the built wheel with `release/install-manifest.json` only when
  `DEBUGORACLE_RELEASE_TAG` is set.
- Do not update the manifest checksum for an ordinary `main` change: it refers
  to the published release artifact. Update it only when the corresponding
  release artifact is being rebuilt and published.

---

## Coding Rules

### Types

- Full type hints required
- Avoid `Any`

### Data

- Prefer immutable dataclasses
- Use explicit `None`
- Use enums for closed sets

### Errors

- No bare `except`
- Fail early
- Use domain-specific exceptions

### Output

- Must be deterministic
- stdout = result
- stderr = errors

### Third-Party Runtime Libraries

- Runtime dependencies are allowed when they deliver clear net benefit (for example stability, ease of use, maintainability, reliability, or performance).
- Do not reinvent established, well-maintained functionality without project-specific justification.
- Scope: runtime dependencies only; dev/test tooling policy is unchanged.
- PRs adding a runtime dependency must include: problem + why stdlib/current code is insufficient, expected metric gains, security/license/maintenance/transitive-footprint review, determinism/reproducibility impact, and alternatives rejected.
- If public behavior changes, link the affected spec in the same PR.

---

## Determinism

Do not introduce:

- time-dependent behavior
- uncontrolled randomness
- unstable ordering
- non-deterministic serialization

---

## Testing

- Test all public behavior changes
- Prefer real I/O over mocks (except external systems)
- Tests must verify determinism

Avoid:

- “no exception” tests

Test types:

- unit
- integration
- HIL (optional, excluded by default)

---

## Constraints

Do not:

- introduce hidden state
- mutate artifacts
- mix parsing, logic, rendering
- bypass specs for public changes
- perform broad refactors without reason

---

## Mental Model

Work with **evidence**, not assumptions.

Focus on:

- what is proven
- what is missing
- what is reproducible
- what is traceable

Avoid:

- implicit inference
- modifying source data
- overstating certainty
