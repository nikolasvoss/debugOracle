# DebugOracle — Agent Guide

## Purpose

DebugOracle is a **passive embedded debugging evidence system**.

It **does not control hardware or execute debugging decisions**.

Instead, it:

- ingests raw debug data (GDB MI, RTT, memory, registers, docs)
- structures it into **deterministic evidence artifacts**
- exposes that evidence for **humans and AI agents**

**Core idea:**

> Turn a live debug session into a reproducible, queryable evidence set.

---

## Core Invariants (Do Not Break)

These define the system. Everything else is secondary.

1. **Deterministic**
   - Same inputs → same outputs
   - No hidden state or randomness

2. **Evidence-first**
   - No inferred or guessed state in artifacts
   - Everything must trace back to a source

3. **Read-only by default**
   - No mutation of target system
   - No implicit control of debugger/hardware

4. **Reproducible**
   - Artifacts must allow offline reconstruction of reasoning

5. **Explicit provenance**
   - Every piece of data must be traceable to origin

---

## Repo Guide Status

This guide describes intended architecture and engineering constraints.
It is **not** a guaranteed exact snapshot of the current repository.

If code and guide differ:

1. trust the code for actual behavior
2. preserve the core invariants
3. update specs or this guide if behavior has changed

Do not spend excessive effort reconciling minor structural drift.

---

## System Model

Conceptually, DebugOracle follows this pipeline:

1. **Acquire** — ingest raw debug data
2. **Normalize** — parse and structure inputs
3. **Reduce** — extract relevant state snapshots
4. **Persist** — store immutable artifact bundles
5. **Render** — present evidence for humans and agents

Implementation details may change.
This model must not.

---

## Architecture (Implementation Snapshot)

Current implementation roughly follows:

- CLI-driven execution (`argparse`)
- Python (3.10+), synchronous
- Immutable artifact model (`dataclasses`, frozen)
- File-based workspace (`.dbgoracle/`)

Typical responsibilities include:

- session/config handling
- debug data ingestion (GDB MI, RTT)
- artifact building
- rendering (text/JSON)
- optional documentation ingestion

This section is descriptive, not prescriptive.
Do not depend on exact module names unless required.

---

## Efficiency Expectations

Operate with strict token and context discipline.

### Read policy
- Start with the minimum set of files needed
- Do not scan the repository broadly by default
- Expand scope only when blocked by missing evidence

### Search boundaries
Start with at most:
1. one relevant spec
2. one implementation file
3. one nearby test

Only expand if necessary.

### Change policy
- Prefer the smallest correct patch
- Avoid opportunistic refactors
- Do not rewrite working code for style
- Do not broaden scope without clear need

### Output policy
- Keep explanations short and technical
- Do not restate the task unless needed
- Avoid long plans for simple tasks
- Report only:
  1. what changed
  2. why it changed
  3. what was validated

---

## Spec-First Workflow

Before modifying any module:

1. Locate its spec in `docs/specs/`
2. Read the spec (purpose, contracts, entrypoints)
3. Read the implementation
4. Read a relevant test if behavior is non-trivial
5. Update the spec if public behavior changes

Specs define **intent and contracts**, not implementation.

---

## Task Execution Order

For most tasks:

1. Read relevant spec
2. Read minimal implementation
3. Read nearest test
4. Make smallest correct change
5. Run targeted validation
6. Expand validation only if needed

Do not explore unrelated modules unless required.

---

## Coding Guidelines

### Type System
- Full type hints required (PEP 484)
- Use modern syntax (`X | Y`)
- Avoid `Any` unless justified

### Data Modeling
- Prefer immutable dataclasses (`frozen=True`)
- Use explicit `None` for optional values
- Use enums for closed sets

### Error Handling
- No bare `except`
- Fail early at boundaries
- Use domain-specific exceptions

### Output Philosophy
- CLI output must be deterministic
- stdout → user output
- stderr → errors

Logging frameworks are avoided by default to preserve determinism.

---

## Testing Principles

- New or changed public behavior must be tested
- File I/O should generally not be mocked
- External systems should be mocked

Test categories:
- unit
- integration
- hardware-in-loop (HIL)

HIL tests must be explicitly marked and optional.

---

## Local Validation Workflow

Use the narrowest validation that fits the change.

### Standard checks

```bash
ruff check .
ruff format --check .
pyright debugoracle/
pytest tests/ -x -q --tb=short --ignore=tests/debugoracle-hil-tests
```
### Auto-fix workflow 
ruff check . --fix
ruff format .
pyright debugoracle/
pytest tests/ -x -q --tb=short --ignore=tests/debugoracle-hil-tests

### Validation scope
- small/local change → targeted checks first
- broader change → full relevant validation
- HIL only when hardware behavior is affected

Ruff = linting/formatting

Pyright = type safety

---

## CLI Design Principles

The CLI is:

- deterministic
- stateless
- composable

Commands:

- read inputs
- produce artifacts or reports
- do not mutate external systems

Future interfaces may extend beyond CLI.

---

## Workspace Model

```
<workspace>/
├── .dbgoracle/
│   ├── latest_snapshot.json
│   ├── session.rtt
│   ├── gdb_mi.log
│   └── ...
```

Artifacts are:

- immutable
- versioned
- replaceable

---

## What Not to Do

- Do not introduce hidden state
- Do not mutate artifacts after creation
- Do not mix parsing, logic, and rendering
- Do not bypass specs for public changes
- Do not scan broadly for context without need
- Do not restate the task unnecessarily
- Do not generate long plans for simple tasks
- Do not perform broad refactors without reason

---

## Quality Constraints

Every change must:

- preserve core invariants
- pass type checks (`pyright`)
- pass relevant tests
- maintain determinism
- avoid security issues:
    - no `shell=True`
    - validate paths
    - control file access

---

## Key Entry Points (Conceptual)

- CLI entry → execution surface
- Bundle builder → core transformation
- Session config → workspace state
- Renderers → output

Names may change; roles must remain.

---

## Mental Model for Agents

You are not debugging the target system.

You are working with **evidence**.

Focus on:

- what is proven
- what is missing
- what is reproducible
- what is traceable

Avoid:

- implicit assumptions
- hidden inference
- modifying source data
- overstating certainty