# cli

- Module: `cli`
- Code Path: `debugoracle/cli/__init__.py`
- Public Entrypoints: `main`
- Last Updated: `2026-04-05`

# SPEC: DebugOracle CLI

## Purpose

DebugOracle is an agent-first CLI for collecting, stabilizing, and rendering embedded debug evidence.
It packages bounded GDB/MI and optional RTT artifacts into a reusable snapshot, then renders a
human-readable report or structured inspection payloads from that evidence.

The CLI does not drive the debugger, write to target memory, or execute LLM calls.

## Product Boundary

DebugOracle is evidence-first.

- It extracts and stabilizes debug evidence.
- It is workspace-aware only for artifact discovery and path resolution.
- It does not read source code.
- It does not interpret the VS Code workspace as a full investigation context.

The agent using DebugOracle is expected to own the broader investigation context, including:

- the VS Code workspace
- source code
- project structure
- any additional files needed for diagnosis

DebugOracle supplies debug evidence to that agent. The agent combines that evidence with source and
workspace context to produce a good answer.

## Product Model

The compatibility package exposes the stable `debugoracle.cli.main` entrypoint while the
implementation lives in:

- `debugoracle/cli/main.py` for parser construction and dispatch
- `debugoracle/cli/commands/status_capture.py` for `status` and `capture-rtt`
- `debugoracle/cli/commands/run_stop.py` for `run` and `stop`
- `debugoracle/cli/commands/find_tcl_port.py` for `find-tcl-port`
- `debugoracle/cli/commands/guard_openocd_launch.py` for `guard-openocd-launch`
- `debugoracle/cli/commands/docs_cli.py` for `docs ingest`, `docs search`, and `docs status`
- `debugoracle/cli/commands/evidence.py` for `fetch` and `report`
- `debugoracle/cli/commands/install_cli.py` for the internal Linux installer hook
- `debugoracle/cli/commands/uninstall_cli.py` for the internal Linux uninstall hook
- `debugoracle/cli/commands/init_workspace.py` for `init-workspace`

The CLI has six behavioral layers:

1. CLI lifecycle
   Commands: internal `install-cli` and `uninstall-cli` entrypoints used by Linux launchers
2. Workspace bootstrap
   Command: `init-workspace`
   Readiness commands: `doctor host`, `workspace plan`, `session doctor`
3. Local reference-manual sidecar
   Commands: `docs ingest`, `docs search`, `docs status`
4. Transport and workspace health
   Commands: `status`, `capture-rtt`, `run`, `stop`, `find-tcl-port`, `guard-openocd-launch`
5. Evidence capture and stabilization
   Command: `fetch`
6. Evidence rendering and inspection
   Command: `report`

## Shared Inputs

### Workspace

- `--workspace-root` defines the root used for discovery and relative-path resolution.
- If omitted, the current working directory is the workspace root.

Workspace awareness is limited to locating relevant debug artifacts. It does not include reading or
interpreting source files.

### Raw Evidence

Raw evidence is file-based only.

- GDB/MI transcript: `--gdb-mi`
- RTT log: `--rtt`

Valid raw combinations:

- GDB/MI only
- RTT only
- GDB/MI and RTT together

Missing evidence weakens the result but does not invalidate `fetch` when at least one selected
source is available.

### Stable Evidence

- Snapshot file: `--snapshot-file`
- Optional SVD file during `fetch`: `--svd-file`
  `fetch --svd-file <file>` opts into halted live peripheral capture; builder-level SVD parsing stays catalog-only unless fetch enables it explicitly.

Snapshots are reusable, machine-readable evidence bundles previously written by `fetch`.
`report` resolves only snapshots; it does not accept raw evidence inputs.
Snapshot completeness is defined by embedded source sections, not by raw sidecar export metadata.

### Output

- Primary payload goes to `stdout` by default.
- `--output` writes the primary payload to a file instead of `stdout`.
- Discovery notices, warnings, and fatal error messages go to `stderr`.

## Command Contracts

### `init-workspace`

Purpose:
- Initialize local DebugOracle workspace capabilities without contacting a
  debugger or target.

Explicit mode:
- Requires `--executable` and at least one `--openocd-config`.
- Creates the existing owned Cortex-Debug scaffold or emits attach/merge actions
  under the established ownership and `--force` rules.

Automatic mode:
- `--auto` makes executable, SVD, and OpenOCD flags optional and consumes the
  bounded local workspace-plan inventory.
- `--yes` is valid only with `--auto` and authorizes parsing PDFs discovered
  under `doc/` or `docs/`; without it, candidates are reported but not parsed.
- Explicit automatic-mode dependency paths must be readable regular files
  contained by the workspace and must not traverse symlinks.
- Documentation, debug-scaffold, and register-catalog capabilities are applied
  independently, then re-inventoried before rendering.
- The JSON payload is versioned, deterministic, provenance-aware, and ordered as
  `documentation`, `debug_scaffold`, `register_catalog`.
- Automatic mode never downloads resources, builds firmware, executes discovered
  strings, launches subprocesses, opens sockets, or contacts a target.

Outputs:
- Text or JSON on `stdout`, with `complete`, `partial`, or `failed` overall and
  per-capability status plus exact next actions.
- Exit `0` for complete, `2` for partial, and `1` for failed.
- A docs-only successful initialization is partial and searchable immediately.

### `status`

Purpose:
- Inspect workspace freshness and artifact health without mutating evidence.

Inputs:
- Workspace root
- Optional explicit overrides for snapshot, GDB/MI, RTT, and RTT state sidecar

Outputs:
- Session-health summary in `text` or `json`

Meaning:
- Reports what artifacts exist, whether they are stale, and whether managed RTT capture metadata looks healthy.

### `capture-rtt`

Purpose:
- Connect to an OpenOCD RTT TCP endpoint and write a raw RTT log.

Inputs:
- Host, port, output path
- Optional state sidecar path
- Connect timeout, poll interval, idle timeout, append mode

Outputs:
- Raw RTT file
- Small capture-state sidecar

Meaning:
- Low-level one-shot transport command. It does not build snapshots.

### `run`

Purpose:
- Manage RTT capture for a workspace in foreground or detached mode.

Inputs:
- Workspace root
- Host, port
- Optional output/state paths
- Connect timeout, poll interval, idle timeout, append mode
- `--detach` for background execution

Outputs:
- Managed RTT log and runtime metadata in the workspace artifact area

Meaning:
- Convenience wrapper around RTT capture for the normal workspace flow.

### `stop`

Purpose:
- Stop the detached RTT capture started by `run --detach`.

Inputs:
- Workspace root
- Optional runtime metadata override
- Grace timeout before force-kill fallback

Outputs:
- Human-readable status line

Meaning:
- Stops only managed DebugOracle run processes and cleans up stale runtime metadata.

### `find-tcl-port`

Purpose:
- Find the active OpenOCD Tcl endpoint for the current workspace session without depending on startup-log capture.

Inputs:
- Workspace root
- Optional OpenOCD PID override
- Optional fetch-command rendering flag and JSON output flag

Outputs:
- Human-readable endpoint summary or JSON payload
- Optional ready-to-run `dbgoracle fetch ... --openocd-tcl-port <port>` command when an SVD file resolves

Meaning:
- `find-tcl-port` is the supported agent-facing discovery surface for the current session's Tcl port.
- It prefers the OpenOCD process whose working directory matches the workspace root.

### `guard-openocd-launch`

Purpose:
- Fail early when a generated attach launch would compete with an already-running workspace-matching OpenOCD session.

Inputs:
- Workspace root

Outputs:
- Human-readable preflight pass/fail message

Meaning:
- `guard-openocd-launch` is the launch-preflight guard used by generated attach-mode tasks.
- It reuses shared OpenOCD workspace matching without starting, stopping, or killing sessions.

### `install-cli`

Purpose:
- Drive the Linux-first installer as a thin launcher hook over the Python installer core.

Inputs:
- Installer manifest URL
- Optional package-source override for local or release-backed `pipx` installation
- Optional auto-accept behavior for PATH profile updates

Outputs:
- Structured installer outcome with explicit success, blocked, failure, PATH, and doctor-note messaging

Meaning:
- `install-cli` is intentionally narrow and hidden from everyday CLI help.
- It exists so the Linux launcher can reuse package-owned installer logic instead of embedding install policy in shell.

### `uninstall-cli`

Purpose:
- Drive Linux uninstall as a thin launcher hook over existing installer backend and platform helpers.

Inputs:
- Optional `--keep-path` to skip shell profile edits
- Optional `--force-legacy-path-cleanup` to remove unmarked matching PATH lines
- `--format` (`text` or `json`)

Outputs:
- Structured uninstall outcome with explicit success, blocked, failure, and PATH-cleanup metadata

Meaning:
- `uninstall-cli` is intentionally narrow and hidden from everyday CLI help.
- It removes the pipx package and only cleans installer-managed PATH lines by default.

### `init-workspace`

Purpose:
- Bootstrap a supported DebugOracle workspace for the installed CLI path.

Inputs:
- Workspace root
- Required executable path
- Optional workspace-default SVD path
- Optional RTT-related workspace defaults

Outputs:
- Scaffolded `.dbgoracle` and `.vscode` files when safe
- `text` or `json` status with created files, blocked files, required follow-up actions, and dependency checks

Meaning:
- `init-workspace` is a setup helper, not an evidence command.
- It refuses to overwrite existing user-owned VS Code config files by default.
- It may return `partial` when setup is recoverable but needs follow-up edits or software dependencies.

### `fetch`

Purpose:
- Build a stable self-contained snapshot from current raw evidence and save it.

Inputs:
- Raw evidence, by explicit path or discovery
- Optional `--state-out`
- Optional `--svd-file` for embedded register catalog capture
- Optional repeatable `--mem ADDR:SIZE` for bounded read-only memory capture
- Optional workspace-default `debugoracle.svdFile` from `.vscode/settings.json` when no explicit SVD flag is provided

Outputs:
- Snapshot JSON written to disk
- Operational summary naming:
  - snapshot id
  - output path
  - embedded sources
  - source sizes and counts

Meaning:
- `fetch` always builds from raw evidence.
- It never treats an existing snapshot as the primary source.
- It overwrites the default latest snapshot when no explicit output path is provided.
- It remains a capture-only surface; register discovery and inspection happen through `report`.
- `fetch --mem` persists deterministic per-range success/failure entries and bounded counters in provenance.

### `report`

Purpose:
- Render a snapshot-only evidence inspection surface.

Inputs:
- Snapshot input only

Outputs:
- Human-readable plain-text report by default
- Compact JSON inspect payloads for:
  - `--vars [NAME ...]`
  - `--gdb [--tail N]`
  - `--rtt [--tail N]`
  - `--regs-list [PERIPHERAL]`
  - `--regs [SELECTOR ...]`
  - `--mem [ADDR:SIZE ...]`
  - `--verbose [--tail N]`

Meaning:
- `report` never rebuilds from raw evidence.
- Full embedded source payloads remain inside the snapshot and can be surfaced through inspect modes.
- `--regs-list` is the discovery surface for captured register catalogs, while `--regs` is the stored-value/status surface.
- The default text report deduplicates primary evidence gaps into the `Gaps` section and avoids repeating the same remediation line across sections.
- Default text `Next Useful Commands` are gated by usable embedded data (for example, RTT tail hints appear only when embedded RTT lines are present).
- Default text source-availability output distinguishes source presence from usable content by including embedded event/line counts when available.

## Source Resolution

### Explicit Inputs Override Discovery

Explicit user-provided paths always win over discovery.

Resolution priority:

1. explicit command-line paths
2. discovered workspace-root artifacts
3. discovered `.dbgoracle` artifacts

### Discovery Candidates

Workspace root candidates:

- `latest_snapshot.json`
- `cortex-debug-shared-mi.log`
- `session.rtt`

Session-directory candidates:

- `.dbgoracle/latest_snapshot.json`
- `.dbgoracle/cortex-debug-shared-mi.log`
- `.dbgoracle/session.rtt`

Each artifact is discovered independently. Partial discovery is valid.

Examples:

- only GDB/MI found: build degraded evidence from GDB/MI only
- only RTT found: build degraded evidence from RTT only
- snapshot found and no raw found: `report` may use the discovered snapshot

All auto-discovered choices must be reported on `stderr`.

Discovery is a convenience layer, not the core product identity. The durable contract is the resolved
evidence source that a command uses after explicit inputs and discovery have been applied.

## Evidence Semantics

### GDB/MI Parsing

- MI records are parsed in transcript order.
- Order is preserved in the resulting event stream.
- Non-MI lines are retained as context, not discarded.
- Console-output and prompt-marker lines are classified explicitly.
- MI parse failures are represented as warning events, not fatal errors.
- Raw lines must remain recoverable from the embedded snapshot source payloads.

### RTT

- RTT is optional context.
- RTT absence must surface as an evidence gap, not an input-resolution failure.
- RTT inclusion is bounded so the artifact remains compact and reviewable.

### Snapshot Integrity

- Snapshots are stable self-contained evidence artifacts intended for later reuse.
- User-facing rendering commands fail hard on unreadable or malformed snapshot JSON.
- Evidence weakness inside a valid snapshot is represented inside the payload, not as snapshot corruption.

## Warnings and Failures

### Warning Model

Weak or incomplete evidence is non-fatal by default.

Examples:

- missing GDB/MI during `fetch`
- missing RTT during `fetch`
- missing selected sources for `report`
- non-MI transcript noise
- MI parse warnings
- thin stop context

Warnings must appear in both places:

- immediate human-visible notices on `stderr`
- structured evidence fields inside the payload or snapshot

The CLI should prefer salvage over rejection:

- raw evidence captured by `fetch` is better than no evidence
- partial evidence is better than failing early
- missing context must be surfaced explicitly instead of silently hidden

### Exit Codes

- `0`: command succeeded, even if evidence is partial
- `1`: operational failure
- `2`: expected resolution/connect failure
- `130`: interrupted by user

`init-workspace` uses its capability contract: `0` for complete, `2` for
partial/actionable progress, and `1` for failed. This is intentionally more
specific than the evidence-command conventions below.

Examples for `1`:

- unreadable required file
- malformed snapshot JSON
- backend/process operation failed
- invalid command argument after parsing

Examples for `2`:

- no valid input source under the requested input mode
- RTT connect timeout

## Invariants

- The CLI is read-only with respect to the debugger and target.
- Primary payload never mixes with notices on `stderr`.
- Explicit flags always override discovery.
- Command meaning must be inferable from the command name.
- Degraded evidence is surfaced explicitly, not silently hidden.
- A saved snapshot is a stable self-contained artifact distinct from raw logs.
- DebugOracle does not read source code or claim to answer source-level questions by itself.
- The agent using DebugOracle is responsible for combining debug evidence with source and workspace context.

## Deliberate Exclusions

- No public `live-status`, `live-registers`, or `live-memory` commands
- No stdin-based raw evidence ingestion
- No live-follow mode for MI or RTT through rendering commands
- No target writes, expression evaluation, or side-effectful probe actions
- No implicit LLM invocation

## Future Direction

Additional live evidence gathering is still in scope, but not as ad hoc public CLI commands.
The intended future shape is a read-only, agent-facing tool surface that can request narrowly
bounded extra target state after snapshot-based evidence has been exhausted.
