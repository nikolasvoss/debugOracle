# Installer Version Metadata Risk Register

Status: Complete

Task: [Installer Version Metadata Task Spec](INSTALLER_VERSION_METADATA_TASK_SPEC.md)

| ID | Risk | Tier | Required control | Exit evidence |
| --- | --- | --- | --- | --- |
| R-001 | Release surfaces drift again. | Low | One canonical source plus a regression test. | Targeted test passes. |
| R-002 | Manifest pin names a different package. | Low | Test asserts the exact pinned source version. | Targeted test passes. |
| R-003 | CLI reports a stale build version. | Low | CLI imports the canonical source. | CLI assertion passes. |
