# Fast-Pass Verification Plan (Eng Reviewed)

## Summary
Lock a minimal, deterministic 2-tier verification flow for agents:
1. `fast` preflight for quick iteration (`coverage` skipped).
2. `full` gate for completion (`pre-commit run --all-files`, unchanged source of truth).

Step 0 verdict: scope is good, no scope reduction needed (small diff, no new services/classes).

## Key Implementation Changes
- Add one wrapper command: `scripts/verify.sh` with modes:
  - `fast` (default): `SKIP=coverage pre-commit run --all-files`
  - `full`: `pre-commit run --all-files`
- Keep `.pre-commit-config.yaml` unchanged (no hook churn, no threshold changes).
- Add clear failure guidance in wrapper output:
  - if `pre-commit` missing, print exact install command and exit non-zero.
- Update workflow docs to prevent ambiguity:
  - `docs/workflows/plan-template.md`: include both commands, mark `full` as required completion gate.
  - `docs/workflows/review-checklist.md`: keep `full` mandatory, optionally record `fast` preflight.
  - `README.md`: explain when to run `fast` vs `full`.
- Do not touch CI workflow now (`.github/workflows/quality-and-traceability.yml` remains full gate only).

## Architecture, Quality, and Performance Review
- Architecture: good reuse of existing quality stack (`.pre-commit-config.yaml`), no parallel verification system.
- Code quality: keep logic centralized in one script to avoid duplicated shell snippets across docs/agents.
- Performance: expected faster loop from skipping coverage while preserving lint/type/test/security checks.
- Risk to control: false confidence from fast-pass; mitigated by explicit docs/checklist language that full gate is mandatory.

## Test Plan

```text
ENTRY: scripts/verify.sh
  |
  +-- mode=fast (default)
  |    -> run SKIP=coverage pre-commit run --all-files
  |    -> non-zero on any remaining hook failure
  |
  +-- mode=full
  |    -> run pre-commit run --all-files
  |    -> non-zero on any hook failure
  |
  +-- invalid mode
       -> print usage + exit non-zero
```

Required tests:
1. `fast` mode invokes `SKIP=coverage` and `--all-files`.
2. `full` mode invokes plain `pre-commit run --all-files`.
3. invalid mode returns non-zero with usage text.
4. missing `pre-commit` path returns non-zero with actionable install hint.
5. docs/tests assert full gate is still required in review checklist and plan template text.

## Assumptions and Defaults
- Target plan is the fast-pass plan from this chat.
- Default mode is `fast`.
- Coverage is the only skipped hook in fast mode.
- Full verification remains mandatory before declaring work complete.
- No CI/branch-protection changes in this slice.
