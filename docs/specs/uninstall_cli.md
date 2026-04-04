# uninstall_cli

- Module: `uninstall_cli`
- Code Path: `debugoracle/cli/commands/uninstall_cli.py`
- Public Entrypoints: `cmd_uninstall_cli`
- Last Updated: `2026-04-04`

# SPEC: Internal Uninstall CLI Hook

## Purpose

Provide a narrow CLI surface that a Linux launcher can call to remove DebugOracle safely.

## Responsibilities

- Reuse existing installer backend/platform helpers for pipx state and PATH profile handling.
- Remove the `debugoracle` pipx package when installed.
- Prompt interactive users before uninstalling bundled docs tooling from the same pipx environment.
- Clean shell-profile PATH lines only when they are installer-managed by marker.
- Emit structured outcomes in `text` or `json` form.
- Always target package name `debugoracle`; do not derive uninstall target from installer manifests.

## Constraints

- Hidden from normal user-facing help.
- Non-interactive and JSON output mode must remain deterministic (no prompt).
- Must not delete workspace artifacts or docs sidecars.
- Must keep legacy unmarked PATH lines untouched by default unless explicitly forced.
