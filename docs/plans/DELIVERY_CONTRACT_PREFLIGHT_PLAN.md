# Delivery Contract and Release Preflight Plan

**Status:** Complete

## Task Link

`docs/plans/DELIVERY_CONTRACT_PREFLIGHT_TASK_SPEC.md`

## Implementation Steps

1. Extend the task-spec template and workflow rules with the delivery contract.
2. Add a Python helper that renders runtime requirements from `pyproject.toml`.
3. Route the artifact CI audit through that helper.
4. Add a read-only release readiness command with explicit failure output.
5. Document the required native CI branch-protection checks.

## Acceptance Criteria -> Validation Map

| AC ID | Validation | Location |
| --- | --- | --- |
| AC-001 | Regression | `tests/test_delivery_contract.py` |
| AC-002 | Unit/subprocess | `tests/test_runtime_requirements.py` |
| AC-003 | Unit/subprocess | `tests/test_release_readiness.py` |
| AC-004 | Regression | `tests/test_delivery_contract.py` |

## Validation Commands

- `python3 -m unittest tests.test_delivery_contract tests.test_runtime_requirements tests.test_release_readiness`
- `./scripts/verify.sh fast`
- `./scripts/verify.sh full`
