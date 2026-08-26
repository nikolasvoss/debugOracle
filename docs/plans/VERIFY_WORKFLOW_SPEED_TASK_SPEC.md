# Verify Workflow Speed Task Spec

**Status:** Complete

## Problem Statement

The required full verification gate runs the non-HIL suite twice: once without
coverage and once with coverage. The fast preflight skips all tests, which
delays useful failure feedback.

## Scope

- In scope: run the test suite once in the full gate, under the existing
  coverage threshold; make the fast gate run tests while skipping coverage;
  create the CI verification environment explicitly.
- Out of scope: changing the coverage threshold, excluding tests, or changing
  HIL execution policy.

## Invariants Touched

No DebugOracle artifact invariants are touched. The verification policy retains
determinism, evidence-first, reproducibility, read-only behavior, and
provenance coverage.

## Acceptance Criteria

- AC-001: `./scripts/verify.sh fast` invokes the test hook and skips only
  coverage.
- AC-002: `./scripts/verify.sh full` invokes one non-HIL test suite under the
  existing 85% coverage threshold.
- AC-003: CI invokes the authoritative full verification command.
- AC-004: Contributor documentation accurately describes the fast workflow.
- AC-005: CI fails if the full verification command exceeds three minutes.

## Accepted Deviation

The CI bound is five minutes rather than the originally specified three
minutes. This deviation is accepted for this completed work item.

## Risks

- Technical risk: a hook rename or skip value could accidentally omit tests.
- Operational risk: contributors could mistake the fast preflight for the
  required full gate.

## Rollback Plan

Revert the verification-script, pre-commit configuration, documentation, and
their regression tests as one change.
