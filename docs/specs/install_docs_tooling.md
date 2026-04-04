# install_docs_tooling

- Module: `install_docs_tooling`
- Code Path: `debugoracle/installer/docs_tooling.py`
- Public Entrypoints: `install_docs_tooling`, `DocsToolingOutcome.as_dict`
- Last Updated: `2026-04-03`

# SPEC: Optional Docs Tooling Install Backend

## Purpose

Provide one deterministic backend for installing optional third-party docs tooling
dependencies after `dbgoracle` is already installed.

## Responsibilities

- Define supported docs-tool profiles: `none`, `docling`, `semantic`, `all`.
- Map each profile to deterministic dependency requirements.
- Validate install preconditions before injecting dependencies:
  - `pipx` must be available on `PATH`
  - `debugoracle` must already be installed in `pipx`
- Execute `pipx inject` for selected requirements when applicable.
- Return structured deterministic outcomes for both humans and automation.

## Output Contract

`DocsToolingOutcome.as_dict()` returns:

- `code`
- `success`
- `message`
- `selection`
- `requirements`
- `remediation`

`code` values currently used:

- `success_skipped`
- `success_installed`
- `blocked_missing_pipx`
- `blocked_missing_debugoracle`
- `failed_pipx_state`
- `failed_inject`
- `failed_invalid_selection`

## Profile Mapping

- `none` -> `[]`
- `docling` -> `["docling"]`
- `semantic` -> `["sentence-transformers", "numpy"]`
- `all` -> `["docling", "sentence-transformers", "numpy"]`

## Constraints

- Linux-first installer flow; no platform-expansion behavior in this module.
- Read-only preflight checks; no mutation outside `pipx inject` call path.
- Deterministic remediation messages for every non-success outcome.
- Must remain aligned with shell wrappers:
  - `scripts/install/bootstrap.py`
  - `scripts/install/linux.sh`
