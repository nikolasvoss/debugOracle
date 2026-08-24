# Python 3.12-only Runtime Support Task Spec

Status: Planned

## Problem Statement

DebugOracle currently promises Python 3.10 through 3.14 support even though
the authoritative release environment is Python 3.12. Maintaining the broad
matrix adds CI and compatibility-maintenance cost without a confirmed user
need.

## Scope

- In scope: release `0.3.1` supports Linux with Python 3.12.x only.
- In scope: package metadata, installer policy, release manifest, CI, active
  documentation, and contract tests state the same policy.
- Out of scope: support for another Python minor, platforms, or architectures.
- Out of scope: changing the published 0.3.0 artifact or its manifest.

## Invariants Touched

- Deterministic: identical source and release inputs produce the same wheel.
- Reproducible: package metadata and release manifest identify the same Python
  requirement and wheel.
- Explicit provenance: the release manifest hash and size derive from the
  final 0.3.1 wheel.

## Acceptance Criteria

- AC-001: `0.3.1` declares `>=3.12,<3.13` in package metadata and its release
  manifest.
- AC-002: the installer blocks Python below 3.12 before backend or network
  mutation and blocks non-3.12 versions through the manifest requirement.
- AC-003: CI runs all quality and artifact gates on Python 3.12 without the
  3.10--3.14 compatibility matrix.
- AC-004: active public installation documentation promises Python 3.12.x
  only; historical 0.3.0 evidence remains unchanged.
- AC-005: the 0.3.1 wheel, manifest hash/size, release URLs, and CLI version
  are consistent and pass the release gate.

## Rollback Plan

Revert the source, manifest, documentation, and CI change as one release
follow-up. No user data or target state is modified.
