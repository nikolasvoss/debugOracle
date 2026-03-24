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
- Support an explicit attach mode for existing Cortex-Debug workspaces by emitting merge-ready VS Code fragments instead of mutating user-owned files.
- Require explicit OpenOCD config file input for the generated Cortex-Debug launch profile.
- Refuse to overwrite existing user-owned VS Code config files by default.
- Emit machine-usable follow-up actions when setup is blocked by existing files.
- Check local software dependencies and report them as part of setup status.
- Store stable workspace defaults, including OpenOCD config files and an optional SVD path, for later flows.

## Command Contract

`dbgoracle init-workspace`:

- creates missing scaffold files in a target workspace for fresh-mode setup
- supports `--attach` for existing workspaces and returns merge-ready VS Code fragments instead of editing user-owned config files
- returns `complete`, `partial`, or `failed`
- uses exit code `0` for `complete`, `2` for `partial`, and `1` for `failed`
- emits `text` or `json` output, including launch identity metadata and the next human action

## Safety Rules

- Existing `.vscode/settings.json`, `.vscode/launch.json`, and `.vscode/tasks.json` are treated as user-owned unless they carry a DebugOracle ownership marker.
- `--attach` never silently mutates user-owned VS Code files; it emits merge-ready fragments for the coding agent instead.
- `--force` only overwrites files previously created by `dbgoracle init-workspace`.
- Blocked files must produce explicit remediation output rather than a vague merge warning.

## OpenOCD Launch Contract

- `--openocd-config <path>` is required and repeatable on `init-workspace`.
- When it is missing, `init-workspace` must fail before writing scaffold files and emit actionable remediation text instead of only a generic parser error.
- The remediation text must explain why the config is needed, show at least one valid `interface/*.cfg` + `target/*.cfg` example, and point the user to existing `configFiles` values when a Cortex-Debug launch already works.
- Fresh-mode scaffold generation writes a runnable `launch.json` with a stable DebugOracle launch identity.
- `--attach` emits a dedicated DebugOracle launch fragment with a stable launch name and role marker so agents can merge it into existing `launch.json` content deterministically.
- `--with-rtt` must switch the generated launch or launch fragment from a plain MI-only launch to an RTT-managed launch, including active `monitor rtt ...` commands plus the matching DebugOracle prelaunch/post-debug tasks.
- The OpenOCD config list is stored in `.vscode/settings.json` or the attach settings fragment as stable workspace metadata.
- `init-workspace` does not generate a fallback launch profile without OpenOCD config files.

## Version Reporting Contract

- `init-workspace` reports the minimum supported Cortex-Debug version in dependency output.
- The minimum version is informational only in this slice; it does not block scaffold generation.

## SVD Default Contract

- `--svd-file <path>` stores `debugoracle.svdFile` in workspace settings.
- `fetch --svd-file <path>` still has highest priority.
- When `fetch` has no explicit `--svd-file`, it may use `debugoracle.svdFile` from `.vscode/settings.json` before falling back to `.dbgoracle/*.svd` discovery.
