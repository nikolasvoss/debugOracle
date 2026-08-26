# Python 3.12-only Runtime Support Risk Register

Status: Planned

| ID | Risk | Mitigation | Gate |
| --- | --- | --- | --- |
| R-001 | Manifest does not match the uploaded wheel. | Compute hash and size from the final 0.3.1 wheel only. | Release verification |
| R-002 | Version drift across package, CLI, URLs, and tests. | Update canonical version first and retain version-contract tests. | Full verification |
| R-003 | Unsupported Python reaches pipx or network operations. | Test early installer rejection and manifest-based rejection. | Installer tests |
| R-004 | Existing unrelated plan/spec edits are overwritten. | Inspect and preserve the dirty diff before editing any overlap. | Review |
| R-005 | Removing the Python matrix accidentally withdraws macOS or Windows installer support. | Retain the 3.12 installer platform matrix, launcher scripts, and platform documentation claims. | Workflow and launcher contract tests |
| R-006 | A 3.10+ readiness or launcher message remains after installer policy changes. | Test core installer, host readiness, and both PowerShell wrappers against the 3.12 policy. | Targeted test modules |
