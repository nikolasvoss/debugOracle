# init_workspace

- Module: `init_workspace`
- Code Path: `debugoracle/cli/commands/init_workspace.py`
- Public Entrypoints: `cmd_init_workspace`
- Last Updated: `2026-08-19`

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
- Support an opt-in local-only automatic mode that applies documentation,
  debug-scaffold, and register-catalog capabilities independently.

## Command Contract

`dbgoracle init-workspace`:

- creates missing scaffold files in a target workspace for fresh-mode setup
- supports `--attach` for existing workspaces and returns merge-ready VS Code fragments instead of editing user-owned config files
- returns `complete`, `partial`, or `failed`
- uses exit code `0` for `complete`, `2` for `partial`, and `1` for `failed`
- emits `text` or `json` output, including launch identity metadata and the next human action

`dbgoracle init-workspace --auto`:

- accepts omitted executable, SVD, and OpenOCD inputs and uses the bounded
  `collect_workspace_plan` inventory plus the pure automatic-init planner
- accepts explicit dependency paths only when they are readable, regular,
  symlink-free files contained by the resolved workspace
- treats explicit inputs as higher priority than configured or discovered inputs
- inventories discovered PDFs without parsing them unless `--yes` is present
- applies documentation, debug-scaffold, and register-catalog work independently
- re-inventories after application so rendered provenance and status describe the
  persisted workspace, not only the pre-application plan
- returns `complete`/`0`, `partial`/`2`, or `failed`/`1`

Automatic JSON has schema version `1`, scope `automatic_workspace_init`, and a
fixed capability order: `documentation`, `debug_scaffold`,
`register_catalog`. Each capability includes its status, selected inputs and
provenance, ambiguities, evidence, ordered actions, and a normalized application
result. Transient facts such as "created on this run" or an unchanged-docs skip
flag are omitted so unchanged reruns normalize identically.

Automatic text output reports the same status, selected-input provenance,
ambiguities, and ordered actions in a compact agent-readable form.

## Safety Rules

- Existing `.vscode/settings.json`, `.vscode/launch.json`, and `.vscode/tasks.json` are treated as user-owned unless they carry a DebugOracle ownership marker.
- `--attach` never silently mutates user-owned VS Code files; it emits merge-ready fragments for the coding agent instead.
- `--force` only overwrites files previously created by `dbgoracle init-workspace`.
- Blocked files must produce explicit remediation output rather than a vague merge warning.
- Automatic mode performs no build, subprocess launch, network request, socket
  connection, OpenOCD/debugger transport, or target action.
- Discovered strings remain data and are never executed.
- Automatic mode does not follow symlinks or accept explicit inputs outside the
  workspace.
- A per-document ingest failure or blocked scaffold file does not roll back or
  suppress another capability.

## OpenOCD Launch Contract

- `--openocd-config <path>` is required and repeatable on `init-workspace`.
- When it is missing, `init-workspace` must fail before writing scaffold files and emit actionable remediation text instead of only a generic parser error.
- The remediation text must explain why the config is needed, show at least one valid `interface/*.cfg` + `target/*.cfg` example, and point the user to existing `configFiles` values when a Cortex-Debug launch already works.
- Fresh-mode scaffold generation writes a runnable `launch.json` with a stable DebugOracle launch identity.
- `--attach` emits a dedicated DebugOracle launch fragment with a stable launch name and role marker so agents can merge it into existing `launch.json` content deterministically.
- `--with-rtt` must switch the generated launch or launch fragment from a plain MI-only launch to an RTT-managed launch, including active `monitor rtt ...` commands plus the matching DebugOracle prelaunch/post-debug tasks.
- The generated RTT launch and generated RTT helper task must both reference the same workspace setting, `debugoracle.rttPort`, instead of embedding separate port literals.
- The OpenOCD config list is stored in `.vscode/settings.json` or the attach settings fragment as stable workspace metadata.
- `init-workspace` does not generate a fallback launch profile without OpenOCD config files.
- Attach-mode generated prelaunch tasks must fail early when a workspace-matching OpenOCD process is already running so `DebugOracle: Attach STM32` does not compete with a manual `make debug` session.
- In automatic mode, explicit `--openocd-config` values win. Otherwise only one
  unambiguous, validated Cortex-Debug `configFiles` list may be reused. Raw
  discovered `.cfg` files are evidence only and are never paired automatically.
- Existing explicit-mode required-input, attach, ownership, `--force`, output,
  and exit-code behavior remains unchanged.

## Version Reporting Contract

- `init-workspace` reports the minimum supported Cortex-Debug version in dependency output.
- The minimum version is informational only in this slice; it does not block scaffold generation.

## SVD Default Contract

- `--svd-file <path>` stores `debugoracle.svdFile` in workspace settings.
- `fetch --svd-file <path>` still has highest priority.
- When `fetch` has no explicit `--svd-file`, it may use `debugoracle.svdFile` from `.vscode/settings.json` before falling back to `.dbgoracle/*.svd` discovery.
- Automatic mode accepts exactly one direct `.dbgoracle/*.svd` as the existing
  default. An explicit or configured SVD outside that directory is persisted to
  `debugoracle.svdFile` only by creating a new DebugOracle-managed settings file,
  matching an existing setting, or updating a DebugOracle-managed file under
  the existing `--force` contract. User-owned settings are never overwritten.

## Documentation Contract

- Automatic documentation candidates come only from the shared bounded
  `doc/`/`docs/` discovery path, including `docs/vendor/`.
- `--auto` without `--yes` reports candidates and the exact authorization action
  without invoking a parser or writing a sidecar.
- `--auto --yes` uses the existing `pypdf`, lexical-index, and atomic sidecar
  ingestion path. It does not enable semantic embeddings.
- Documentation-only success is overall `partial` with exit code `2` when the
  hardware capabilities remain unavailable. The indexed document is immediately
  available to `dbgoracle docs search` without an embedded toolchain.
- Per-document diagnostics are retained in the structured application result;
  parser-library stderr does not leak into the primary CLI streams.

## Idempotence

- An automatic rerun skips byte-identical managed scaffold files without
  requiring `--force` and without changing their mtimes.
- Existing docs freshness checks prevent unchanged sidecar rewrites.
- Source PDFs, ELF/SVD/config inputs, and user-owned VS Code files are never
  modified.
