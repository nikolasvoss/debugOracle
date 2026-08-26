# Cross-Platform Installer Plan

Status: Active

Task: [Cross-Platform Installer Task Spec](CROSS_PLATFORM_INSTALLER_TASK_SPEC.md)

Security review: Complete — high-risk controls are mandatory implementation
requirements; atomic user-configuration writes and a release-time dependency
audit remain tracked delivery work.

## Delivery Sequence

1. Add the macOS and Windows launcher contracts and a shared bootstrap entry
   point without changing installer policy.
2. Replace Linux-only platform guards with an explicit platform-adapter
   selection boundary.
3. Extend the pipx backend to query its effective application binary directory.
4. Implement macOS PATH markers and a Windows user-scoped, atomically written
   managed-entry record. Every user-configuration write uses a same-directory
   temporary file, flush/sync, and atomic replace; no cleanup occurs when
   ownership is ambiguous.
5. Route uninstall through the same adapters and preserve output compatibility.
6. Add unit, launcher, and native install lifecycle tests; extend CI to all
   supported OS/architecture cells.
7. Add the release-time dependency vulnerability audit, run full verification,
   and record compatibility evidence.

## Acceptance Criteria to Validation

| Acceptance criterion | Validation |
| --- | --- |
| AC-001, AC-002 | Launcher and adapter tests; native checkout smoke tests. |
| AC-003, AC-004 | Pipx-path and managed-PATH lifecycle regression tests. |
| AC-005 | Install/uninstall CLI contract tests on every platform job. |
| AC-006 | Existing trust-boundary tests executed on every platform job. |
| AC-007 | CI workflow and release compatibility-matrix evidence. |
