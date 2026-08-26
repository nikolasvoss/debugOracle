# Python 3.12-only Runtime Support Test Plan

Status: Planned

## Coverage

| Scenario | Expected result |
| --- | --- |
| Package and 0.3.1 manifest requirements | Both equal `>=3.12,<3.13`. |
| Installer with Python 3.11 | `blocked_missing_python` before backend or network activity. |
| Installer with Python 3.12 | Continues to manifest validation and normal install flow. |
| Installer with Python 3.13 or 3.14 | Manifest requirement rejects the version without pipx mutation. |
| Host readiness with Python 3.11 | Python readiness item is blocked. |
| PowerShell launchers without Python | State Python 3.12 as the requirement. |
| CI workflow | No 3.10--3.14 matrix; quality and artifact gates use 3.12; installer contract gates remain on Linux, both macOS runners, and Windows with 3.12. |
| Documentation | Active user-facing claims name Python 3.12.x only and retain the supported Linux/macOS/Windows platform list. |
| Release artifact | Repeated builds match; manifest hash/size, wheel filename, and CLI version are 0.3.1. |

## Commands

- `./scripts/verify.sh fast` during implementation.
- `./scripts/verify.sh full` before completion.
- `./scripts/verify-release.sh` after recording the final artifact metadata.

## Targeted Test Modules

- `tests/test_installer.py` and `tests/test_installer_backend_manifest.py`
- `tests/test_cli_flow.py` for host-readiness output
- `tests/test_platform_launchers.py`
- `tests/test_release_packaging.py`, `tests/test_release_version_metadata.py`,
  and `tests/test_verify_workflow_docs.py`
