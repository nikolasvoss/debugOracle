# install_cli

- Module: `install_cli`
- Code Path: `debugoracle/cli/commands/install_cli.py`
- Public Entrypoints: `cmd_install_cli`
- Last Updated: `2026-04-04`

# SPEC: Internal Installer CLI Hook

## Purpose

Provide a narrow CLI surface that a Linux launcher can call to reuse the package-owned installer core.

## Responsibilities

- Translate parser arguments into installer-core options.
- Render installer outcomes in `text` or `json` form.
- Keep install policy out of shell wrappers while accepting launcher-provided source overrides.
- Accept checkout-local package source overrides from the Linux launcher.

## Constraints

- Hidden from normal user-facing help.
- Must not broaden the ordinary debug-evidence workflow surface.
- Must preserve structured outcome mapping from the installer core instead of flattening failures into generic text.

## Version Consistency Contract

- The package build version and `dbgoracle --version` derive from the canonical
  `debugoracle.version.__version__` value.
- The checkout manifest's `version` and public GitHub tag archive `source_url`
  must match that canonical version.
- The checkout launcher must continue to pass its local repository path as the
  package source override. That override takes precedence over the manifest
  source so an audited checkout installs its own contents.
- The `0.2.0` public alpha is not published through PyPI.
- A regression test must reject drift among these release metadata surfaces
  before a checkout installer run can report a false verification failure.

## Verified Alpha Environment

- Release evidence is produced on Ubuntu 24.04 LTS x86-64 with Python 3.12 and
  `pipx`.
- Other distributions, architectures, and Python versions are unverified for
  the `0.2.0` public alpha.
