# Cross-Platform Installer Task Spec

Status: Active

## Problem Statement

The supported checkout installer and uninstaller are Linux-only despite the
package being Python/pipx based. Windows and macOS users need an equally direct,
native, verified install and uninstall path.

## Scope

- In scope: current macOS on Apple Silicon and Intel; current Windows with the
  current PowerShell; the existing Linux path remains supported.
- In scope: one checkout-local install command and one checkout-local uninstall
  command per operating system.
- In scope: safe, idempotent, reversible platform-specific PATH handling.
- Out of scope: installers for Python, pipx, Homebrew, Scoop, drivers, IDEs,
  OpenOCD, and user-selectable DebugOracle install paths.

## Invariants Touched

- Deterministic: identical installer inputs yield the same structured outcome.
- Evidence-first: release and compatibility claims are backed by native CI or
  recorded manual evidence.
- Read-only target: installation never mutates the debug target or workspace
  artifacts.
- Explicit provenance: remote release artifacts retain existing manifest and
  checksum verification before pipx mutation.

## Acceptance Criteria

- AC-001: macOS and Windows provide documented native checkout install and
  uninstall launchers that delegate policy to the shared Python bootstrap.
  The PowerShell launcher passes an argument array directly, never evaluates a
  command string, bypasses execution policy, or requests elevation.
- AC-002: Linux, macOS, and Windows use explicit platform adapters; any other
  platform produces the existing structured unsupported-platform outcome.
- AC-003: verification and PATH handling use pipx's effective app-bin
  directory, including a pre-existing pipx configuration, without adding a
  DebugOracle configuration choice.
- AC-004: install and uninstall change only platform-specific PATH state that
  they can prove they manage; reruns are idempotent. All user-configuration
  writes are atomic. Windows persists an atomic, user-scoped managed-entry record
  and removes a PATH entry only when that record and the current exact entry
  agree; absence, duplication, or disagreement requires manual remediation.
- AC-005: fresh install, upgrade, verification, failure recovery, and uninstall
  retain stable text and JSON outcome behavior on each supported OS.
- AC-006: manifest validation, redirect validation, artifact checksum/size, and
  package/version identity validation occur before pipx mutation on each
  supported OS.
- AC-007: CI/release evidence covers Linux, current Windows/current PowerShell,
  current Apple Silicon macOS, and current Intel macOS.

## Rollback Plan

Revert launchers, platform adapters, platform CI jobs, documentation, and tests
as one change. Uninstall never removes unmarked user PATH entries, so rollback
does not require modifying user state.
