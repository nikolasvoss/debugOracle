### 1. Current State

- Work is partly spec-driven already:
  - Product/system intent in [strategy.md](/home/niko/Dokumente/Bastelei/ai-debugger-v2/docs/strategy.md), [architecture.md](/home/niko/Dokumente/Bastelei/ai-debugger-v2/docs/architecture.md), and module specs index [README.md](/home/niko/Dokumente/Bastelei/ai-debugger-v2/docs/specs/README.md).
  - Engineering workflow/invariants in [AGENTS.md](/home/niko/Dokumente/Bastelei/ai-debugger-v2/AGENTS.md).
- Validation is strong locally:
  - Required command is `pre-commit run --all-files` in [AGENTS.md](/home/niko/Dokumente/Bastelei/ai-debugger-v2/AGENTS.md).
  - Gates in [.pre-commit-config.yaml](/home/niko/Dokumente/Bastelei/ai-debugger-v2/.pre-commit-config.yaml): Ruff, Pyright, pytest, coverage>=85, Bandit.
  - Invariants specified and contract-tested in [testing-requirements.md](/home/niko/Dokumente/Bastelei/ai-debugger-v2/docs/specs/testing-requirements.md) and [test_core_invariants.py](/home/niko/Dokumente/Bastelei/ai-debugger-v2/tests/contracts/test_core_invariants.py).
- Key weaknesses:
  - No repo-visible CI workflow for mandatory enforcement.
  - No canonical, enforced task-spec template and acceptance-to-test mapping.
  - Plans exist (Phase 1–5 in `docs/plans`) but remain partially aspirational and not merge-gated.
  - Strong runtime reproducibility exists; decision reproducibility is weak (why a behavior/decision changed is not systematically captured).

### 2. Viability

- Expected impact: **High**.
- Integration difficulty: **Medium**.
- Cost model:
  - Expected overhead: `+10–20%` on non-trivial behavior changes.
  - Expected overhead on small fixes: low if lightweight path is allowed.
  - Expected benefit: lower regression risk in invariant-sensitive areas, faster/clearer review for multi-module changes, stronger traceability.
- Where this helps most:
  - CLI/public behavior changes.
  - Artifact/schema/model changes.
  - Multi-module flows where spec/test drift currently appears.

### 3. Open Questions

- Is CI intentionally external or currently absent for this repo?
- What is the canonical planning artifact going forward (`docs/plans/*` vs PR template)?
- What exact changes should force full workflow?
- Who approves exceptions when acceptance criteria lack direct tests?
- Are Phase 3–5 testing plans in `docs/plans` current commitments or backlog proposals?

### 4. Risks

- Risk: process overhead slows delivery.
  - why: full workflow applied too broadly.
  - impact: medium.
  - mitigation: strict boundary for “full” vs “lightweight” workflow.
- Risk: spec drift continues.
  - why: docs/tests not required by changed behavior.
  - impact: high.
  - mitigation: diff-aware CI gate requiring spec/test updates for behavior changes.
- Risk: local-only quality checks.
  - why: pre-commit not centrally enforced.
  - impact: high.
  - mitigation: CI mirror of `pre-commit run --all-files`, branch protection.
- Risk: checklist theater.
  - why: specs/plans authored without acceptance-to-validation links.
  - impact: medium.
  - mitigation: hard rule: each acceptance criterion maps to test or explicit manual validation step.

### 5. Tooling

- What exists already:
  - Specs, architecture docs, invariants, contract tests, pre-commit quality stack.
- What can be reused:
  - `docs/specs` registry pattern.
  - `tests/contracts` structure.
  - Existing phase-plan format in `docs/plans/TESTING_PLAN_PHASE_*.md`.
- What is missing:
  - CI definition in repo.
  - Canonical task-spec/plan/checklist templates.
  - Diff-aware enforcement:
    - if behavior-relevant files change, require linked spec + test delta.
  - Review template that enforces links: spec, plan, tests, acceptance criteria mapping.

### 6. Gaps

- Desired workflow: spec-driven + agent-assisted + reproducible implementation decisions.
- Current gap:
  - strong code/test discipline exists, but workflow traceability is not enforced.
  - acceptance criteria are not systematically operationalized into tests/validation.
  - “decision reproducibility” (why changed) is not first-class.

### 7. Minimal Setup

- Folder structure:
  - `docs/workflows/task-spec-template.md`
  - `docs/workflows/plan-template.md`
  - `docs/workflows/review-checklist.md`
- Workflow steps:
  1. Task spec: problem, scope, invariants touched, acceptance criteria.
  2. Plan: modules/files affected, decomposition, test updates.
  3. Implement.
  4. Validate: `pre-commit run --all-files`.
  5. Traceability gate: each acceptance criterion -> test or explicit manual validation.
  6. Review: checklist-based, with links to spec/plan/tests.
- Required tooling:
  - CI mirror of pre-commit.
  - Diff-aware CI check:
    - detect behavior-impacting diffs
    - require spec update and test update when needed.
  - PR template enforcing traceability fields.

### 8. Adoption Plan

- Strategy: **full rollout now** for behavior-changing work, with a documented lightweight path for non-behavior changes.
- Rollout rule:
  - If behavior can change, full workflow is mandatory.
  - If behavior cannot change (docs/comments/refactor-only), lightweight path allowed.
- Enforcement date:
  - Effective immediately after CI + PR template + workflow docs merge.

### 9. Exact Implementation Plan

#### 9.1 Create canonical workflow artifacts

1. Add `docs/workflows/task-spec-template.md` with required fields:
   - Problem statement
   - Scope / out-of-scope
   - Invariants touched
   - Acceptance criteria (ID-tagged, e.g. `AC-001`)
   - Risks and rollback
2. Add `docs/workflows/plan-template.md` with required fields:
   - Files/modules to change
   - Test plan mapped to acceptance criteria
   - Validation commands
   - Release/compatibility notes
3. Add `docs/workflows/review-checklist.md` with required checks:
   - Spec linked
   - Plan linked
   - Every AC mapped to test or explicit manual validation
   - Invariants reviewed
   - `pre-commit run --all-files` output attached

#### 9.2 Solo-v1 PR traceability contract (reduced scope)

1. Add `.github/pull_request_template.md` with mandatory sections:
   - `Spec:` link
   - `Plan:` link
   - `Acceptance Criteria -> Validation:` mapping table
   - `Behavior Change:` `yes` or `no` (manual declaration, no auto-classifier yet)
2. Reuse and extend existing `docs/workflows/AGENT_WORKFLOW_RULES.md` as the single source of truth for workflow boundaries (no new boundary doc in v1).

#### 9.3 Solo-v1 CI enforcement in repo

1. Add `.github/workflows/quality-and-traceability.yml`:
   - Trigger: PR + push to `main`
   - Job `quality-gate`: run `pre-commit run --all-files`
   - Job `traceability-gate`: simple deterministic check for required PR fields when `Behavior Change: yes`
2. Do not add `scripts/ci/traceability_gate.py` in v1.
   - Use minimal inline shell/Action logic first.
   - Promote to dedicated Python script only if false positives/negatives appear repeatedly.

#### 9.4 Repository protection (minimum)

1. In GitHub branch protection for `main`, require status checks:
   - `quality-gate` job from `quality-and-traceability.yml`
   - `traceability-gate` job from `quality-and-traceability.yml`
2. Require pull request before merge.
3. Disable force-push for `main`.
4. Record chosen branch protection settings in this plan after rollout so setup is reproducible.

#### 9.5 Exceptions policy (minimum)

1. Do not create `docs/workflows/exceptions.md` in v1.
2. Add a concise "exception handling" section directly to `docs/workflows/AGENT_WORKFLOW_RULES.md`:
   - allowed exception cases
   - required justification in PR
   - one-PR expiry

#### 9.6 Verification checklist (must pass before declaring complete)

1. CI runs on a PR and both jobs execute.
2. A behavior-changing sample PR fails when spec/plan/AC mapping is missing.
3. The same PR passes after adding required fields.
4. A docs-only PR with `Behavior Change: no` passes.
5. `pre-commit run --all-files` passes locally.

#### 9.7 Definition of done (solo v1)

- Done when all are true:
  - workflow templates exist in `docs/workflows/`
  - PR template merged and used by default
  - combined CI workflow merged and green
  - branch protection enforces the two required checks
  - exception rules are documented in `AGENT_WORKFLOW_RULES.md`
  - at least one merged behavior-changing PR demonstrates `spec -> plan -> test -> code`

#### 9.8 Deferred (explicitly out of v1 scope)

- `scripts/ci/traceability_gate.py` classifier (defer until repeated CI misclassification pain).
- separate `docs/workflows/workflow-boundary.md` (reuse existing rules doc instead).
- separate `docs/workflows/exceptions.md` (keep policy inline for now).

Worth doing: **Yes**. Implement the reduced solo-v1 workflow now, enforce it in CI, and add heavier automation only after real failure evidence.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 2 | CLEAR | 10 proposals, 7 accepted, 5 deferred (latest logged run) |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 4 | CLEAR | 10 issues reviewed in current session, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

- **CROSS-MODEL:** Outside-voice plan review previously flagged issues; this eng review kept scope minimal and deterministic.
- **UNRESOLVED:** 0
- **VERDICT:** CEO + ENG CLEARED — ready to implement. Eng review required gate is satisfied by current session review outcome.
