# Agent Workflow Rules

Mandatory rules for branch and spec handling.

## Decision Rules

| Situation | New Branch | New Spec |
|---|---:|---:|
| New feature | Yes | Yes |
| Public behavior change | Yes | Yes |
| User-visible CLI behavior change | Usually yes | Yes |
| Artifact/schema/model/storage contract change | Usually yes | Yes |
| Current branch has unrelated work | Yes | If behavior changes, yes |
| Docs-only edit | No | No |
| Comment/docstring-only edit | No | No |
| Formatting-only edit | No | No |
| Refactor proven behavior-preserving by existing tests | No | No |

If uncertain, treat the change as behavior-affecting: create a branch and a spec.

## Branch Rules

- Use task-scoped, descriptive names (example: `feat/spec-traceability-gate`).
- Do not mix unrelated features on one branch.

## Spec and Plan Rules

- Public behavior changes without a task spec are not allowed.
- Public behavior changes must include a task plan.
- Specs must define acceptance criteria IDs (example: `AC-001`).
- Each acceptance criterion must map to:
  - a test, or
  - explicit manual validation when a test is not feasible.
- PRs with behavior changes must include:
  - `Spec:` link
  - `Plan:` link
  - `Acceptance Criteria -> Validation` mapping table with at least one non-header row

## Exception Handling (Solo-v1)

- Exceptions are allowed only when the full workflow would block urgent progress.
- Every exception must be documented in the PR body under `Exception Justification` with:
  - what is being skipped,
  - why it is safe for this PR,
  - what follow-up work closes the gap.
- Exception validity expires with that single PR. Reusing a prior exception is not allowed.
