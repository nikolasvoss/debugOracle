# Installer Version Metadata Task Spec

Status: Complete

## Problem Statement

The package metadata, release manifest, and CLI version reported different
versions, causing the supported checkout installer to fail verification after
installing a functional CLI.

## Scope

- In scope: one canonical package/CLI version, matching manifest release
  metadata, and a regression guard.
- Out of scope: changing installer policy, pipx behavior, or release channels.

## Invariants Touched

- Deterministic: identical checkout metadata yields identical installer
  verification results.
- Reproducible: the manifest identifies the same artifact version the CLI
  reports.

## Acceptance Criteria

- AC-001: package build metadata and `dbgoracle --version` use one canonical
  version value.
- AC-002: the checkout manifest version and pinned package source match the
  canonical version.
- AC-003: automated tests reject any metadata drift.

## Risks

- Technical risk: a future release could update only one metadata surface.
- Operational risk: a stale manifest could make checkout installs report a
  failure despite a working binary.

## Rollback Plan

Revert the version-source module, packaging configuration, manifest, and
regression test as one atomic change; no persisted user data changes.
