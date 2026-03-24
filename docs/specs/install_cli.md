# install_cli

- Module: `install_cli`
- Code Path: `debugoracle/cli/commands/install_cli.py`
- Public Entrypoints: `cmd_install_cli`
- Last Updated: `2026-03-24`

# SPEC: Internal Installer CLI Hook

## Purpose

Provide a narrow CLI surface that a Linux launcher can call to reuse the package-owned installer core.

## Responsibilities

- Translate parser arguments into installer-core options.
- Render installer outcomes in `text` or `json` form.
- Keep install policy out of shell wrappers.
- Let the resolved manifest choose the package source instead of forcing checkout-local installs from the launcher.

## Constraints

- Hidden from normal user-facing help.
- Must not broaden the ordinary debug-evidence workflow surface.
- Must preserve structured outcome mapping from the installer core instead of flattening failures into generic text.
