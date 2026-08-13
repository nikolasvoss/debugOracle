# Installer Version Metadata Test Plan

Status: Complete

Task: [Installer Version Metadata Task Spec](INSTALLER_VERSION_METADATA_TASK_SPEC.md)

| Area | Required coverage | Acceptance criteria |
| --- | --- | --- |
| Package/CLI | Build metadata and `--version` share one source. | AC-001 |
| Manifest | `version` and pinned `source_url` equal the source value. | AC-002 |
| Regression | Targeted tests and the full pre-commit suite pass. | AC-003 |

## Validation Sequence

1. Run `python3 -m unittest tests.test_release_version_metadata`.
2. Run `./scripts/verify.sh fast`.
3. Run `./scripts/verify.sh full`.
