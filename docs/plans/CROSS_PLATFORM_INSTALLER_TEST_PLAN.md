# Cross-Platform Installer Test Plan

Status: Active

Task: [Cross-Platform Installer Task Spec](CROSS_PLATFORM_INSTALLER_TASK_SPEC.md)

Purpose: prove that the supported checkout installer and uninstaller behave
identically in intent on Linux, macOS, and native Windows without weakening the
manifest, artifact, or package-identity trust controls.

## Acceptance Criteria to Validation

| Area | Required coverage | Acceptance criteria |
| --- | --- | --- |
| Launchers | macOS shell and Windows PowerShell launchers forward supported options to the shared Python bootstrap; local checkout source overrides remain non-user-controllable. | AC-001 |
| Platform selection | Linux, macOS, and Windows select explicit platform adapters; unsupported platforms return stable `blocked_platform` output. | AC-002 |
| pipx paths | The backend resolves the effective `PIPX_BIN_DIR` through pipx and uses it for verification and PATH actions; overrides remain honoured. | AC-003 |
| PATH lifecycle | Each adapter is idempotent, records only its own change, and uninstall removes only that recorded managed change. | AC-004 |
| Installation lifecycle | On every supported OS: fresh install, same-version rerun, upgrade, verification failure, and uninstall preserve the documented structured outcome contract. | AC-005 |
| Trust regressions | Invalid manifest, redirect, checksum, size, and package/version identity failures happen before pipx mutation on all supported platforms. | AC-006 |
| Release evidence | CI executes the relevant test suites on Linux, current macOS on Apple Silicon and Intel, and current Windows with the current PowerShell. | AC-007 |

## Validation Sequence

1. Add adapter, backend, launcher, and uninstall unit tests for every acceptance
   criterion.
2. Run native checkout install/uninstall smoke tests in isolated user homes on
   Linux, macOS, and Windows.
3. Run `./scripts/verify.sh fast` locally where available.
4. Run `./scripts/verify.sh full` before completion.
5. Attach CI and manual architecture evidence to the compatibility matrix.
