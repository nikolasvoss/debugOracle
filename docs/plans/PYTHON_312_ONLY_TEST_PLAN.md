# Python 3.12-only Runtime Support Test Plan

Status: Planned

## Coverage

| Scenario | Expected result |
| --- | --- |
| Package and 0.3.1 manifest requirements | Both equal `>=3.12,<3.13`. |
| Installer with Python 3.11 | `blocked_missing_python` before backend or network activity. |
| Installer with Python 3.12 | Continues to manifest validation and normal install flow. |
| Installer with Python 3.13 or 3.14 | Manifest requirement rejects the version without pipx mutation. |
| CI workflow | No 3.10--3.14 matrix; quality and artifact gates use 3.12. |
| Documentation | Active user-facing claims name Python 3.12.x only. |
| Release artifact | Repeated builds match; manifest hash/size, wheel filename, and CLI version are 0.3.1. |

## Commands

- `./scripts/verify.sh fast` during implementation.
- `./scripts/verify.sh full` before completion.
- `./scripts/verify-release.sh` after recording the final artifact metadata.
