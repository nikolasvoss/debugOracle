# cli

- Module: `cli`
- Code Path: `debugoracle/cli/__init__.py`
- Public Entrypoints: `main`
- Last Updated: `2026-03-18`

# SPEC: DebugOracle CLI

## Purpose

DebugOracle is an agent-first CLI for collecting, stabilizing, and rendering embedded debug evidence.
It packages bounded GDB/MI and optional RTT artifacts into a reusable snapshot, then renders either a
human report or an agent-ready prompt from that evidence.

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
- `debugoracle/cli/commands/evidence.py` for `observe`, `snapshot`, `report`, and `prompt`

The CLI has three behavioral layers:

1. Transport and workspace health
   Commands: `status`, `capture-rtt`, `run`, `stop`
2. Evidence capture and stabilization
   Command: `observe`
3. Evidence rendering
   Commands: `snapshot`, `report`, `prompt`

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

Missing evidence weakens the result but does not invalidate it.

### Stable Evidence

- Snapshot file: `--snapshot-file`

Snapshots are reusable, machine-readable evidence bundles previously written by `observe`.

### Output

- Primary payload goes to `stdout` by default.
- `--output` writes the primary payload to a file instead of `stdout`.
- Discovery notices, warnings, and fatal error messages go to `stderr`.

## Command Contracts

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

### `observe`

Purpose:
- Build a stable snapshot from current raw evidence and save it.

Inputs:
- Raw evidence, by explicit path or discovery
- Optional `--state-out`
- Optional `--export-raw`

Outputs:
- Snapshot JSON written to disk
- Success line naming the snapshot id and output path

Meaning:
- `observe` always builds from raw evidence.
- It never treats an existing snapshot as the primary source.

### `snapshot`

Purpose:
- Render the current evidence state for inspection or automation.

Inputs:
- Snapshot or raw evidence, according to source resolution rules

Outputs:
- Evidence bundle in `json`, `text`, or `markdown`

Meaning:
- `snapshot` prefers fresh raw evidence.
- It falls back to snapshot input only when raw input is unavailable and input mode allows fallback.

### `report`

Purpose:
- Render a human-facing evidence report.

Inputs:
- Snapshot or raw evidence, according to source resolution rules

Outputs:
- Report in `text` or `markdown`

Meaning:
- `report` prefers a stable snapshot.
- It may rebuild from raw only when explicitly requested by input mode.

### `prompt`

Purpose:
- Render an agent-ready prompt package from stable evidence.

Inputs:
- Snapshot or raw evidence, according to source resolution rules
- Required `--goal`
- Optional intent text or intent file

Outputs:
- Prompt package in `text` or `markdown`

Meaning:
- `prompt` prefers a stable snapshot.
- It may rebuild from raw only when explicitly requested by input mode.

## Source Resolution

### Input Mode

The target CLI defines `--input-mode auto|snapshot|raw` for `snapshot`, `report`, and `prompt`.

- `auto`: use the command default
- `snapshot`: only use snapshot input; fail if no snapshot is available
- `raw`: only use raw input; fail if no raw input is available

Command defaults:

- `observe`: raw only
- `snapshot`: raw first, then snapshot fallback
- `report`: snapshot first
- `prompt`: snapshot first

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
- snapshot found and no raw found: `report` and `prompt` may use snapshot in `auto` mode

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
- Raw lines must remain recoverable through raw export when warnings occur or when explicitly requested.

### RTT

- RTT is optional context.
- RTT absence must surface as an evidence gap, not an input-resolution failure.
- RTT inclusion is bounded so the artifact remains compact and reviewable.

### Snapshot Integrity

- Snapshots are stable evidence artifacts intended for later reuse.
- User-facing rendering commands fail hard on unreadable or malformed snapshot JSON.
- Evidence weakness inside a valid snapshot is represented inside the payload, not as snapshot corruption.

## Warnings and Failures

### Warning Model

Weak or incomplete evidence is non-fatal by default.

Examples:

- missing GDB/MI
- missing RTT
- non-MI transcript noise
- MI parse warnings
- thin stop context

Warnings must appear in both places:

- immediate human-visible notices on `stderr`
- structured evidence fields inside the payload or snapshot

The CLI should prefer salvage over rejection:

- raw evidence is better than no evidence
- partial evidence is better than failing early
- missing context must be surfaced explicitly instead of silently hidden

### Exit Codes

- `0`: command succeeded, even if evidence is partial
- `1`: operational failure
- `2`: expected resolution/connect failure
- `130`: interrupted by user

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
- A saved snapshot is a stable artifact distinct from raw logs.
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
