# Python 3.12-only Runtime Support Risk Register

Status: Planned

| ID | Risk | Mitigation | Gate |
| --- | --- | --- | --- |
| R-001 | Manifest does not match the uploaded wheel. | Compute hash and size from the final 0.3.1 wheel only. | Release verification |
| R-002 | Version drift across package, CLI, URLs, and tests. | Update canonical version first and retain version-contract tests. | Full verification |
| R-003 | Unsupported Python reaches pipx or network operations. | Test early installer rejection and manifest-based rejection. | Installer tests |
| R-004 | Existing local README/test edits are overwritten. | Inspect and merge the dirty diff before editing overlapping files. | Review |
