# Installer Version Metadata Plan

Status: Complete

## Task Link

[Installer Version Metadata Task Spec](INSTALLER_VERSION_METADATA_TASK_SPEC.md)

## Files / Modules To Change

- `debugoracle/version.py`: canonical release version.
- `pyproject.toml`, `debugoracle/cli/main.py`, `release/install-manifest.json`:
  consume or match that version.
- `tests/test_release_version_metadata.py`: drift regression coverage.

## Implementation Steps

1. Introduce a canonical Python version value and have setuptools and the CLI
   use it.
2. Align the release manifest and its package pin.
3. Add a test for package configuration, manifest, and CLI output.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
| --- | --- | --- |
| AC-001 | Unit | `tests/test_release_version_metadata.py` |
| AC-002 | Unit | `tests/test_release_version_metadata.py` |
| AC-003 | Regression | `./scripts/verify.sh full` |

## Release / Compatibility Notes

The CLI reports `0.1.1`, matching the installed package and release manifest.
No command syntax or user data changes.
