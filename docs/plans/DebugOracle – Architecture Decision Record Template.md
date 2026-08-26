# DebugOracle – Architecture Decision Record

Create one copy of this template for each reviewed architectural topic.

Do not combine unrelated topics into one decision.

---

## Decision ID

`ADR-XXX`

## Topic

Example: `GDB/MI ownership`

## Status

- Investigation
- Experiment
- Decided
- Implemented
- Superseded

## Date

YYYY-MM-DD

---

# 1. Question

State one specific architectural question.

Example:

> Should DebugOracle continue maintaining its own general-purpose GDB/MI implementation, or should generic source-level debugging be delegated to gdb-mcp?

---

# 2. Why this matters

Describe:

- user impact,
- maintenance impact,
- architectural impact,
- dependency impact.

Keep this concrete.

---

# 3. Current implementation

Document:

- files,
- classes/functions,
- CLI/API,
- tests,
- consumers,
- dependencies.

Do not evaluate yet.

---

# 4. Problem solved today

Complete:

> The current implementation exists to...

If this cannot be answered clearly, record that.

---

# 5. Strengths of current implementation

- 
- 
- 

---

# 6. Weaknesses of current implementation

- 
- 
- 

Separate observed weaknesses from assumptions.

---

# 7. Alternatives

## Alternative A – Keep current

Description:

Advantages:

Disadvantages:

Risks:

## Alternative B

Description:

Advantages:

Disadvantages:

Risks:

## Alternative C

Description:

Advantages:

Disadvantages:

Risks:

---

# 8. External alternatives inspected

For each relevant project:

## Project

Version/commit reviewed:

Relevant capabilities:

Missing capabilities:

Maintenance state:

Integration complexity:

Licensing/dependency concerns:

Evidence from real test:

---

# 9. Minimal experiment

Describe the smallest test capable of distinguishing the alternatives.

Example:

1. Start OpenOCD.
2. Connect STM32.
3. Connect gdb-mcp using arm-none-eabi-gdb.
4. Set source breakpoint.
5. Continue.
6. Inspect locals.
7. Evaluate expression.
8. Read backtrace.
9. Read memory/registers.
10. Repeat session.

---

# 10. Experiment result

Observed:

Expected:

Failures:

Workarounds required:

Performance:

Reliability:

Agent usability:

Human usability:

---

# 11. Decision criteria

Explicitly state the threshold.

Example:

Replace current implementation only if:

- all required STM32 operations work,
- no critical current use case is lost,
- integration is stable,
- maintenance burden is materially reduced.

---

# 12. Decision

Choose one:

- KEEP
- KEEP + EXTEND
- SIMPLIFY
- REPLACE
- EXTERNALIZE
- DEPRECATE
- REMOVE
- BUILD
- DEFER

Decision:

---

# 13. Reason

Use evidence rather than architectural preference.

---

# 14. Confidence

- LOW
- MEDIUM
- HIGH

Reason:

---

# 15. Minimal implementation change

Describe only the smallest next change justified by this decision.

Do not include unrelated cleanup.

---

# 16. What must NOT change yet

Explicitly protect adjacent architecture.

Examples:

- Do not remove transcript import.
- Do not change SVD models.
- Do not migrate RTT.
- Do not reorganize directories.

This prevents cascading refactors.

---

# 17. Tests required

## Existing tests that must continue passing

- 

## New tests

- 

## Hardware validation

- 

---

# 18. Migration

If replacing existing functionality:

Old:

New:

Compatibility period:

Removal criteria:

---

# 19. Rollback

How can this change be reverted?

---

# 20. Code to remove eventually

Only list code whose replacement has already been validated.

- 

---

# 21. Follow-up questions

These are questions, not automatically approved work items.

- 
- 

---

# 22. Resulting architecture impact

One paragraph maximum.

---

# 23. Scorecard update

Area:

Decision:

Confidence:

Replacement validated:

Next action:

---

# 24. Stop condition

After implementing the minimal approved change:

**STOP.**

Run tests and evaluate results.

Do not automatically proceed into the next architecture topic.

A new ADR is required for the next significant architectural decision.