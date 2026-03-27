# DebugOracle

DebugOracle is a trustworthy embedded-debug evidence engine for chat-driven debugging. It reads a bounded GDB/MI transcript plus optional RTT logs, builds a reusable evidence bundle, and renders grounded inspection output that an agent or engineer can use in the same workspace.

The intended product strategy lives in [`docs/strategy.md`](docs/strategy.md).
The intended system architecture lives in [`docs/architecture.md`](docs/architecture.md).

Module specifications live under [`docs/specs/README.md`](docs/specs/README.md). The spec filename matches the module filename so agents have one predictable place to look for architecture notes.

## Install the CLI

Linux v1 ships a CLI-only installer path. It installs `dbgoracle`; it does not install `openocd`, VS Code, Cortex-Debug, or board-specific tooling.

Prerequisites for the installer itself:

- Linux
- Python 3.10+
- `pipx`

Manifest-driven launcher path from a checkout:

```bash
./scripts/install/linux.sh
```

After `dbgoracle` is installed, the setup script asks whether to install optional docs tooling:

- `docling` for stronger extraction on difficult/scanned PDFs
- semantic search deps (`sentence-transformers`, `numpy`) for hybrid docs search

Non-interactive or scripted installs can choose explicitly:

```bash
./scripts/install/linux.sh --docs-tools none
./scripts/install/linux.sh --docs-tools docling
./scripts/install/linux.sh --docs-tools semantic
./scripts/install/linux.sh --docs-tools all
```

Secondary local-dev path from a checkout:

```bash
pipx install .
```

The launcher follows `release/install-manifest.json`, so the manifest decides which package spec is installed. `pipx install .` is the explicit local checkout path.

If the installer succeeds but `dbgoracle` is not immediately on `PATH`, it offers one managed shell-profile update and also prints the exact line to add manually.

Embedded toolchain checks happen later during workspace setup and capture flows, not during install success.

## Default workflow

DebugOracle does not drive the probe or debugger. The primary near-term workflow is:

1. The engineer asks for help in chat from the same workspace.
2. The agent or engineer starts a Cortex-Debug session with shared MI logging available.
3. Reproduce until the target reaches a meaningful stop.
4. Open or refresh Call Stack, Registers, and Variables or Locals so Cortex-Debug emits the context you want to keep.
5. If runtime breadcrumbs matter, capture RTT from the OpenOCD RTT TCP port with `run` (or low-level `capture-rtt`).
6. Build a reusable snapshot with `fetch`.
7. Inspect the evidence with `report`.

The same CLI commands remain useful as a direct verification and fallback path when the engineer wants to inspect the evidence without the chat workflow.

The most useful MI capture includes:

- `*stopped,...`
- `^done,stack=[...]`
- `^done,register-values=[...]`
- `^done,locals=[...]` or `^done,variables=[...]`

## Commands

### Manual and datasheet docs ingestion

DebugOracle can ingest local manuals/datasheets into a nearby docs sidecar for local search during debugging.

Quick start:

```bash
dbgoracle docs ingest --file doc/STM32F4_Reference_Manual.pdf
dbgoracle docs search "USART baud rate register"
dbgoracle docs status
```

Key points:

- Default parser is `pymupdf` (`pymupdf` + `pymupdf4llm` are installed with base dependencies).
- Optional parser: `--parser docling` (install with `pipx inject debugoracle docling`).
- Optional hybrid search: ingest with `--semantic`, search with `--semantic` (install with `pipx inject debugoracle sentence-transformers numpy`).
- Preflight dependency check: `dbgoracle docs doctor`.
- If you run ingest without `--file`/`--folder`, DebugOracle discovers likely PDFs under `doc/` and `docs/` and requires `--yes` confirmation.
- In TTY mode, ingest can prompt for discovered-doc confirmation; use `--no-interactive` to disable prompts.
- Failed long ingests keep staging checkpoints and can resume compatible reruns.
- Sidecar artifacts are written next to each source as `<source>.dbgoracle-docs/`.

Full usage and troubleshooting:
[`docs/docs-ingestion.md`](docs/docs-ingestion.md)

### Bootstrap a workspace

For a fresh project with an installed CLI, start here:

```bash
dbgoracle init-workspace --workspace-root . --executable build/app.elf --openocd-config interface/stlink.cfg --openocd-config target/stm32l4x.cfg
```

Optional workspace-default SVD path:

```bash
dbgoracle init-workspace --workspace-root . --executable build/app.elf --openocd-config interface/stlink.cfg --openocd-config target/stm32l4x.cfg --svd-file boards/sample.svd
```

`init-workspace` creates `.dbgoracle/` plus the supported `.vscode` scaffold when the workspace is fresh.
If existing VS Code files block automation, it returns `partial` and prints exact follow-up actions.

Software dependencies checked during `init-workspace`:

- `openocd` on `PATH`
- the configured executable path
- the Cortex-Debug VS Code dependency as a reported requirement, including the minimum supported version

### File dependencies by input source

| Input source / capability | Required workspace files | Required software dependencies | Notes |
| --- | --- | --- | --- |
| GDB/MI capture for `fetch` | `.vscode/settings.json`, `.vscode/launch.json`, `.dbgoracle/` | VS Code, Cortex-Debug | Launch config must write MI logs to the configured path. |
| RTT capture via `run` / `stop` | `.dbgoracle/` | `openocd` with RTT endpoint | VS Code files are optional for manual CLI use. |
| Default `fetch -> report` workflow | `.dbgoracle/`, `.vscode/settings.json`, `.vscode/launch.json` | VS Code, Cortex-Debug | `tasks.json` helps automation but is not required for the basic path. |
| Managed prelaunch/postdebug RTT workflow | `.vscode/settings.json`, `.vscode/tasks.json`, `.dbgoracle/` | `openocd` | Active when the launch config references the DebugOracle RTT tasks. |
| Workspace-default SVD for `fetch` | `.vscode/settings.json` | readable SVD file | Stored as `debugoracle.svdFile`. |
| Live peripheral capture with SVD | `.vscode/settings.json` | `openocd`, usable Tcl port, readable SVD file | `init-workspace` stores the default SVD path but does not discover the Tcl port. |

### Easy setup for Cortex-Debug

Use the example below to make first capture quick:

- Merge the entry from `examples/cortex-debug/launch.jsonc.example` into `.vscode/launch.json` (do not replace other launch configurations).
- Merge `examples/cortex-debug/tasks.json.example` into `.vscode/tasks.json` so `.dbgoracle` is created automatically before each debug launch.
- The example tasks start `run --detach` before launch and call `stop` when the debug session ends.

- Run one focused debug stop.
- Build once:

```bash
./dbgoracle fetch
./dbgoracle report
```

Optional halted peripheral capture from an SVD definition:

```bash
./dbgoracle fetch --svd-file examples/STM32L432.svd
./dbgoracle report --regs-list
```

Fetch output path behavior:
- `--state-out` always wins when provided.
- Without `--state-out`, `fetch` writes `latest_snapshot.json` next to the resolved GDB/MI input when available,
  or next to the resolved RTT input, or finally to `<workspace>/.dbgoracle/latest_snapshot.json`.

Before running `fetch`, verify the MI file is receiving output:

```bash
test -s cortex-debug-shared-mi.log && echo "MI log ready" || test -s .dbgoracle/cortex-debug-shared-mi.log && echo "MI log ready" || echo "MI log empty or missing"
```

What to configure in Cortex-Debug:

- MI log path should point to `./cortex-debug-shared-mi.log` or `.dbgoracle/cortex-debug-shared-mi.log`.
- RTT should stay enabled in Cortex-Debug/OpenOCD so the RTT TCP server comes up, but DebugOracle should write `.dbgoracle/session.rtt` via `run` (or `capture-rtt`).
- Keep captures bounded: stop at the event you care about and end the debug session to avoid mixing multiple stops.
- `fetch --svd-file <file>` is the explicit CLI trigger for halted live peripheral capture; builder-level SVD parsing stays catalog-only unless fetch enables it.
- Without `--svd-file`, `fetch` first checks `.vscode/settings.json` for `debugoracle.svdFile`, then falls back to auto-discovering exactly one `.dbgoracle/*.svd` candidate.
- `fetch --svd-file <file>` expects the most recent target-state event in the recent MI tail to still be a stop and uses the default OpenOCD control endpoint for safe peripheral register reads.
- Refresh Call Stack, Registers, and Variables/Locals before capture so the latest stop has rich context.
- Use one RTT consumer only while `run`/`capture-rtt` is attached.

Quick check after run:

- `fetch` succeeds and writes `latest_snapshot.json` in the resolved artifact folder
  (next to explicit/auto-resolved GDB/MI input when present, otherwise next to explicit/auto-resolved RTT,
  otherwise `<workspace>/.dbgoracle`).
- `report` shows stop reason + frame + register/local context.

If `source .vscode/dump-registers.gdb` causes `Python is not supported`, remove that
line from `postLaunchCommands` until you switch to a Python-enabled GDB binary.

See full sample config and step-by-step checklist in [`examples/cortex-debug/README.md`](examples/cortex-debug/README.md).

Typical Cortex-Debug flow:

```bash
./dbgoracle run --detach --workspace-root /path/to/workspace --port 60001 --output /path/to/session.rtt
./dbgoracle fetch --workspace-root /path/to/workspace
./dbgoracle report --workspace-root /path/to/workspace
./dbgoracle stop --workspace-root /path/to/workspace
./dbgoracle --version
```

Automation or inspection-oriented JSON output:

```bash
./dbgoracle report --vars
./dbgoracle report --gdb
./dbgoracle report --verbose
```

## When inspect JSON is useful

- Automation or scripting against saved evidence
- Pulling exact variable groups or embedded GDB/RTT sections from a snapshot
- Feeding a machine-readable inspection payload back into an agent turn
- Attaching a machine-readable inspection payload to an issue or test case

Compact JSON inspect modes are not required for the everyday `fetch -> report` workflow.
New snapshots already embed the full selected raw source payloads plus derived parsed structures,
so `report --gdb`, `report --rtt`, and `report --verbose` can surface them without raw sidecars.

`report` now renders non-MI frequency summaries in explicit form, for example:

- `Unable to match requested speed 500 kHz, using 480 kHz
 (repeated 6 times)`

Note: historical snapshots that only contain the old non-MI pattern format will not show a
top-pattern summary. Rebuild snapshots to use the current structured pattern contract.

## Roadmap and low-level verification

The ranked product roadmap lives in [`ROADMAP.md`](ROADMAP.md).

This slice also adds read-only verification commands for the low-level foundation:

```bash
./dbgoracle status
./dbgoracle run --detach --workspace-root . --port 60001 --output .dbgoracle/session.rtt
./dbgoracle stop --workspace-root .
```

Future live reads are still part of the product direction, but not as public CLI commands in
this slice. The intended path is a read-only agent-facing tool surface for gathering additional
evidence after a snapshot has been inspected.

## Notes and boundaries

- v1 is read-only and does not call an LLM.
- `report` is the primary inspection surface for both agents and engineers.
- If the MI log only contains `*stopped` without follow-up stack, register, or local queries, the snapshot is valid but thinner.
- If the MI log spans several stops, DebugOracle packages the latest stop-context it finds. Keep captures tight and per-stop when possible.
- RTT is optional. Missing RTT weakens the bundle but does not fail the run.
- The supported robust RTT path is `run` (or low-level `capture-rtt`) against the OpenOCD RTT TCP port. Cortex-Debug `rttConfig.logFile` is best-effort only.
- `status` reports RTT transport health separately from the RTT file when `.dbgoracle/session.rtt.state.json` is present.
- MI and RTT inputs are treated as untrusted text. v1 does not guarantee redaction or secret scrubbing.
- Source-context enrichment is not yet collected in this version.
