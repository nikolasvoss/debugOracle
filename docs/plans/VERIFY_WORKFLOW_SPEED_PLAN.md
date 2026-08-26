# Verify Workflow Speed Plan

**Status:** Complete

## Task Link

`docs/plans/VERIFY_WORKFLOW_SPEED_TASK_SPEC.md`

## Files / Modules To Change

- `scripts/verify.sh`
- `.pre-commit-config.yaml`
- `.github/workflows/quality-and-traceability.yml`
- `README.md`
- `tests/test_verify_script.py`

## Implementation Steps

1. Update the public verification-script tests for the desired fast and full
   behavior.
2. Make `fast` skip coverage only.
3. Keep separate fast and coverage test hooks, but skip the fast hook in the
   full gate so that the full suite executes exactly once.
4. Create the CI virtual environment and install the declared development
   tools before routing CI through the authoritative full command.
5. Bound the CI verification command to three minutes.
6. Update contributor-facing documentation.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
|---|---|---|
| AC-001 | integration | `python3 -m unittest tests.test_verify_script` |
| AC-002 | regression | `./scripts/verify.sh full` |
| AC-003 | regression | `python3 -m unittest tests.test_verify_workflow_docs` |
| AC-004 | regression | `python3 -m unittest tests.test_verify_workflow_docs` |
| AC-005 | regression | `python3 -m unittest tests.test_verify_workflow_docs` |

## Test Plan

- Unit: fake `pre-commit` verifies the shell-script contract.
- Integration: run the real fast and full verification commands.
- Regression: run the complete pre-commit suite.

## Validation Commands

- `./scripts/verify.sh fast`
- `./scripts/verify.sh full`
- `pre-commit run --all-files`

## Release / Compatibility Notes

The fast preflight now provides test feedback. The full gate retains all
existing tests and coverage enforcement while avoiding the duplicate run.

## Completion Note

AC-005's original three-minute CI bound is intentionally accepted as a
five-minute bound in the current workflow.
