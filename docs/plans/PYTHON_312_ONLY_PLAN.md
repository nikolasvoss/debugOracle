# Python 3.12-only Runtime Support Plan

Status: Planned

## Task Link

[Python 3.12-only Runtime Support Task Spec](PYTHON_312_ONLY_TASK_SPEC.md)

## Implementation Steps

1. Create branch `codex/feat/python-312-only`. Preserve the current unrelated
   dirty plan/spec edits; inspect the diff before editing any overlap.
2. Set the canonical version to `0.3.1` in `debugoracle/version.py`; update
   release URLs, `changelog.md`, release-verification fixtures, and version
   contract assertions that intentionally describe the current release.
3. Set `pyproject.toml` `requires-python` and the 0.3.1 manifest
   `python_requires` to `>=3.12,<3.13`. Raise the installer and host-readiness
   early Python boundaries and messages to 3.12 while retaining manifest-bound
   PEP 440 validation for 3.13+.
4. Remove the Python compatibility-matrix job and its 3.10-only test setup;
   retain the 3.12 quality and artifact gates and the existing 3.12 installer
   platform matrix for Linux, both current macOS runners, and Windows. Keep
   those platform claims and update both PowerShell launcher messages to 3.12.
5. Remove only the Python-3.10-specific dependency/import fallbacks: the
   conditional `tomli` development dependency and `tomllib` fallbacks in
   release-packaging and public-release contract tests.
6. Update active public docs and contract tests--`README.md`,
   `docs/guides/installation.md`, and `docs/docs-ingestion.md`--to promise
   Python 3.12.x while preserving the supported platform list. Do not rewrite
   archived 0.3.0 audit evidence.
7. After all source changes are complete, build the 0.3.1 wheel twice with the
   fixed release epoch, record that wheel's SHA-256 and byte size in the
   manifest, then run full and release verification before publishing.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
| --- | --- | --- |
| AC-001 | Unit | `tests/test_release_packaging.py`, `tests/test_release_version_metadata.py`, and manifest tests |
| AC-002 | Unit | `tests/test_installer.py`, `tests/test_installer_backend_manifest.py`, and readiness/launcher contract tests with simulated Python versions |
| AC-003 | Regression | `tests/test_verify_workflow_docs.py` and `.github/workflows/quality-and-traceability.yml` contract assertions |
| AC-004 | Regression | README, installation-guide, and docs-ingestion contract assertions; `tests/test_platform_launchers.py` |
| AC-005 | Release | `./scripts/verify.sh full` and `./scripts/verify-release.sh` |

## Release Notes

Release `0.3.1` is intentionally a patch release selected by the maintainer.
The existing 0.3.0 GitHub Release is not altered.
