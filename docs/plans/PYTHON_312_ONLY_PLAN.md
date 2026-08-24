# Python 3.12-only Runtime Support Plan

Status: Planned

## Task Link

[Python 3.12-only Runtime Support Task Spec](PYTHON_312_ONLY_TASK_SPEC.md)

## Implementation Steps

1. Create branch `codex/feat/python-312-only` and preserve the existing dirty
   README/test changes while applying this task.
2. Set the canonical version to `0.3.1`; update release URLs, changelog, and
   version-contract fixtures that intentionally describe the current release.
3. Set `requires-python` and the 0.3.1 manifest `python_requires` to
   `>=3.12,<3.13`. Raise the installer's early Python boundary and its message
   to 3.12 while retaining manifest-bound PEP 440 validation.
4. Remove the compatibility-matrix job, retain quality and artifact gates on
   3.12, and remove only Python-3.10-specific dependency/import fallbacks.
5. Update active public docs and their contract tests to say Python 3.12.x;
   do not rewrite archived 0.3.0 audit evidence.
6. Build the final 0.3.1 wheel twice, record its actual SHA-256 and byte size
   in the manifest, then run full and release verification before publishing.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
| --- | --- | --- |
| AC-001 | Unit | packaging and manifest contract tests |
| AC-002 | Unit | installer policy tests with simulated Python versions |
| AC-003 | Regression | workflow/documentation contract tests |
| AC-004 | Regression | README and installation-guide contract tests |
| AC-005 | Release | `./scripts/verify.sh full` and `./scripts/verify-release.sh` |

## Release Notes

Release `0.3.1` is intentionally a patch release selected by the maintainer.
The existing 0.3.0 GitHub Release is not altered.
