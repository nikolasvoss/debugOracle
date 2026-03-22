# init_workspace

- Module: `init_workspace`
- Code Path: `debugoracle/cli/commands/init_workspace.py`
- Public Entrypoints: `cmd_init_workspace`
- Last Updated: `2026-03-22`

# SPEC: DebugOracle Workspace Bootstrap Command

## Purpose

Own the installed-CLI workspace bootstrap flow for the supported Cortex-Debug/OpenOCD path.

## Responsibilities

- Create the minimum `.dbgoracle` and `.vscode` scaffold for a fresh workspace.
- Refuse to overwrite existing user-owned VS Code config files by default.
- Emit machine-usable follow-up actions when setup is blocked by existing files.
- Check local software dependencies and report them as part of setup status.
- Store an optional workspace-default SVD path for later `fetch` use.

## Command Contract

`dbgoracle init-workspace`:

- creates missing scaffold files in a target workspace
- returns `complete`, `partial`, or `failed`
- uses exit code `0` for `complete`, `2` for `partial`, and `1` for `failed`
- emits `text` or `json` output

## Safety Rules

- Existing `.vscode/settings.json`, `.vscode/launch.json`, and `.vscode/tasks.json` are treated as user-owned unless they carry a DebugOracle ownership marker.
- `--force` only overwrites files previously created by `dbgoracle init-workspace`.
- Blocked files must produce explicit remediation output rather than a vague merge warning.

## SVD Default Contract

- `--svd-file <path>` stores `debugoracle.svdFile` in workspace settings.
- `fetch --svd-file <path>` still has highest priority.
- When `fetch` has no explicit `--svd-file`, it may use `debugoracle.svdFile` from `.vscode/settings.json` before falling back to `.dbgoracle/*.svd` discovery.
