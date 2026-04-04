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
