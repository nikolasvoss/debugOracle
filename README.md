# DebugOracle

DebugOracle is a trustworthy embedded-debug evidence engine for chat-driven debugging. It reads a bounded GDB/MI transcript plus optional RTT logs, builds a reusable evidence bundle, and renders grounded inspection output that an agent or engineer can use in the same workspace.

The intended product strategy lives in [`docs/strategy.md`](docs/strategy.md).
The intended system architecture lives in [`docs/architecture.md`](docs/architecture.md).

Module specifications live under [`docs/specs/README.md`](docs/specs/README.md). The spec filename matches the module filename so agents have one predictable place to look for architecture notes.

## Default workflow

DebugOracle does not drive the probe or debugger. The primary near-term workflow is:

1. The engineer asks for help in chat from the same workspace.
2. The agent or engineer starts a Cortex-Debug session with shared MI logging available.
3. Reproduce until the target reaches a meaningful stop.
4. Open or refresh Call Stack, Registers, and Variables or Locals so Cortex-Debug emits the context you want to keep.
5. If runtime breadcrumbs matter, capture RTT from the OpenOCD RTT TCP port with `run` (or low-level `capture-rtt`).
6. Build a reusable snapshot with `fetch`.
7. Inspect the evidence with `report`.
8. Optionally package the same snapshot with `prompt` for downstream handoff.

The same CLI commands remain useful as a direct verification and fallback path when the engineer wants to inspect the evidence without the chat workflow.

The most useful MI capture includes:

- `*stopped,...`
- `^done,stack=[...]`
- `^done,register-values=[...]`
- `^done,locals=[...]` or `^done,variables=[...]`

## Commands

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

Optional handoff packaging:

```bash
./dbgoracle prompt --goal "Explain why the target stopped here"
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
- `fetch --svd-file <file>` expects the most recent target-state event in the recent MI tail to still be a stop and uses the default OpenOCD control endpoint for safe peripheral register reads.
- Refresh Call Stack, Registers, and Variables/Locals before capture so the latest stop has rich context.
- Use one RTT consumer only while `run`/`capture-rtt` is attached.

Quick check after run:

- `fetch` succeeds and writes `latest_snapshot.json` in the resolved artifact folder
  (next to explicit/auto-resolved GDB/MI input when present, otherwise next to explicit/auto-resolved RTT,
  otherwise `<workspace>/.dbgoracle`).
- `report` shows stop reason + frame + register/local context.
- `prompt` remains available when you want a packaged handoff artifact.

If `source .vscode/dump-registers.gdb` causes `Python is not supported`, remove that
line from `postLaunchCommands` until you switch to a Python-enabled GDB binary.

See full sample config and step-by-step checklist in [`examples/cortex-debug/README.md`](examples/cortex-debug/README.md).

Typical Cortex-Debug flow:

```bash
./dbgoracle run --detach --workspace-root /path/to/workspace --port 60001 --output /path/to/session.rtt
./dbgoracle fetch --workspace-root /path/to/workspace
./dbgoracle report --workspace-root /path/to/workspace
./dbgoracle prompt --workspace-root /path/to/workspace --goal "Explain why the target stopped here"
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

`report` and `prompt` now render non-MI frequency summaries in explicit form, for example:

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
- `prompt` produces optional text or Markdown packaging for downstream handoff.
- If the MI log only contains `*stopped` without follow-up stack, register, or local queries, the snapshot is valid but thinner.
- If the MI log spans several stops, DebugOracle packages the latest stop-context it finds. Keep captures tight and per-stop when possible.
- RTT is optional. Missing RTT weakens the bundle but does not fail the run.
- The supported robust RTT path is `run` (or low-level `capture-rtt`) against the OpenOCD RTT TCP port. Cortex-Debug `rttConfig.logFile` is best-effort only.
- `status` reports RTT transport health separately from the RTT file when `.dbgoracle/session.rtt.state.json` is present.
- MI and RTT inputs are treated as untrusted text. v1 does not guarantee redaction or secret scrubbing.
- Source-context enrichment is not yet collected in this version.
