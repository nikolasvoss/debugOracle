# Cross-Platform Installer Risk Register

Status: Active

Task: [Cross-Platform Installer Task Spec](CROSS_PLATFORM_INSTALLER_TASK_SPEC.md)

Purpose: control the additional platform and persistent-environment risks of
making the checkout installer first-class on macOS and Windows.

| ID | Risk | Tier | Required control | Exit evidence |
| --- | --- | --- | --- | --- |
| R-001 | A Windows launcher invokes an unintended Python interpreter or misquotes a path containing spaces. | High | Resolve and invoke Python using a fixed argument array; prohibit command-string evaluation, execution-policy bypass, and elevation. Test paths with spaces and hostile-looking arguments. | Native Windows launcher tests and smoke evidence pass. |
| R-002 | Incorrect pipx default-path assumptions make an installed CLI unverifiable or edit the wrong PATH location. | High | Query pipx for its effective binary directory; honour pre-existing pipx configuration without exposing a DebugOracle path-selection option. | Adapter/backend tests cover macOS, Windows, configured paths, and legacy locations. |
| R-003 | Uninstall removes a user-owned PATH entry. | High | macOS uses a managed profile marker. Windows atomically records its exact user-scoped entry and refuses removal when the record is missing, duplicated, or differs from PATH. | Negative cleanup tests prove user-owned entries remain untouched. |
| R-004 | Platform support bypasses release-manifest/artifact identity checks. | High | Keep source download, hash, size, redirect, and wheel identity checks in the shared core; platform adapters may not download or select packages. | Existing trust tests run in every supported OS job. |
| R-005 | CI claims support that does not cover Apple Silicon, Intel macOS, or the current Windows shell. | Medium | Test the current supported release on every declared OS/architecture/shell cell and publish the resulting matrix. | Release evidence links to each supported cell. |
| R-006 | Auto-installing package managers/Python increases privilege and supply-chain exposure. | Medium | Keep prerequisite provisioning out of scope; provide deterministic remediation commands only. | Spec and docs state prerequisites and no elevated commands are run. |
| R-007 | Runtime dependency vulnerabilities are not independently audited; the existing quality gate runs static analysis only. | Low | Add a release-time dependency vulnerability audit with a reviewed advisory source and fail on unresolved critical findings. | Release gate records audit output and remediation/exception. |
| R-008 | A failure while rewriting a shell profile or installer record corrupts user configuration. | Medium | Write to a same-directory temporary file, flush/sync, then atomically replace; preserve permissions and test injected write/replace failures. | Failure-injection tests leave the original configuration intact. |
