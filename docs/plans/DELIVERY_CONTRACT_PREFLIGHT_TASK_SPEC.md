# Delivery Contract and Release Preflight Task Spec

**Status:** Complete

## Problem Statement

Recent installer and release work discovered platform and release prerequisites
only after changes reached CI or release preparation. Contributors need
deterministic local checks for those prerequisites and task specifications must
state the delivery evidence needed before implementation completes.

## Scope

- In scope: delivery-contract requirements in the task-spec template and agent
  workflow; a reproducible runtime-dependency requirements helper; a read-only
  release-readiness command; documentation of the required protected CI checks.
- Out of scope: publishing releases, changing GitHub authentication, changing
  release versions, or changing the existing installer implementation.

## Invariants Touched

The commands are deterministic for a fixed checkout and command environment,
read-only with respect to repository and release state, and report provenance
for each failed prerequisite.

## Acceptance Criteria

- AC-001: Relevant task specifications must declare environments, adversarial
  boundaries, and release/operational prerequisites.
- AC-002: Runtime dependencies are rendered from `pyproject.toml` by a
  checked-in command that is used by CI and can be run locally.
- AC-003: A release-readiness command rejects invalid authentication, dirty or
  unsynchronized Git state, metadata drift, and an occupied release tag before
  publication is attempted.
- AC-004: Documentation states that native installer checks must protect
  `main` before merge.

## Risks

- Technical risk: a preflight duplicates release metadata validation.
- Operational risk: GitHub branch protection cannot be applied without a
  maintainer-authenticated GitHub session.

## Rollback Plan

Revert the helper scripts, CI call site, workflow/template text, and focused
tests together. No release, credential, or repository-hosting state is changed
by the repository patch.
