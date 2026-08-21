# DebugOracle

DebugOracle is a trustworthy embedded-debug evidence engine for chat-driven debugging. It reads a bounded GDB/MI transcript plus optional RTT logs, builds a reusable evidence bundle, and renders grounded inspection output that an agent or engineer can use in the same workspace.

The intended product strategy lives in [`docs/strategy.md`](docs/strategy.md).
The intended system architecture lives in [`docs/architecture.md`](docs/architecture.md).

Module specifications live under [`docs/specs/README.md`](docs/specs/README.md). The spec filename matches the module filename so agents have one predictable place to look for architecture notes.

## Hardware-Free Agent Demo

Open
[`examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg`](examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg)
as the root of a new VS Code window and ask:

```text
Initialise this workspace for the DebugOracle demo. Show me what evidence is
available, ingest the bundled demo reference, diagnose the serial failure, and
distinguish observations from documentation and conclusions.
```

The workspace contains a snapshot, firmware sources, and a short project-owned
register reference, so the agent can demonstrate reports plus docs search
without hardware or an embedded toolchain.

### What the agent can prove

The showcase is not generic reasoning over a prompt. DebugOracle gives the
agent traceable access to heterogeneous evidence that normally lives in
separate tools and files. A strong answer from the bundled fixture looks like
this:

> **Recorded observation:** RTT reports
> `OBS: serial_path=fault code=-2`.
>
> **Firmware source:** `app/src/usart.c` requests 115200 baud, while
> `app/src/main.c` switches USART1 to `RCC_USART1CLKSOURCE_HSI`.
>
> **Register evidence:** the snapshot records `RCC_CCIPR = 0x00000002`, so
> USART1 uses HSI16, and `USART1_BRR = 0x000002B6` (decimal 694).
>
> **Bundled reference:** the project-owned register note documents the
> `USART1SEL` meaning and the sampling-by-16 baud relation. With HSI16, the
> observed divider yields about 23,055 baud, not 115200 baud.
>
> **Conclusion:** the sources independently converge on a USART clock/divider
> mismatch. The snapshot proves the recorded state, not the state of a
> currently connected target; a live capture would be the next confirmation.

That provenance boundary matters: runtime text is a symptom, source shows
intent and configuration, registers show recorded device state, and the local
reference supplies the hardware meaning needed to connect them.

The complete ST RM0394 manual is not redistributed and is not required for the
demo. The limited bundled reference is independently written and project-owned.
If you want the full manual, download it yourself from the official
[STM32L4 documentation page](https://www.st.com/en/microcontrollers-microprocessors/stm32l4-series/documentation.html)
and place the PDF under `docs/vendor/`. DebugOracle does not silently download
or redistribute restricted vendor documentation.

## PR workflow (solo v1)

Behavior-changing pull requests are expected to include traceability fields in the PR body:

- `Behavior Change: yes/no`
- `Spec:` link (required when behavior changes)
- `Plan:` link (required when behavior changes)
- `Acceptance Criteria -> Validation` table (required when behavior changes)

Templates and review guides:

- [`.github/pull_request_template.md`](.github/pull_request_template.md)
- [`docs/workflows/task-spec-template.md`](docs/workflows/task-spec-template.md)
- [`docs/workflows/plan-template.md`](docs/workflows/plan-template.md)
- [`docs/workflows/review-checklist.md`](docs/workflows/review-checklist.md)
- [`docs/workflows/AGENT_WORKFLOW_RULES.md`](docs/workflows/AGENT_WORKFLOW_RULES.md)

CI runs `./scripts/verify.sh full` and a traceability gate on PRs.

## Verification loop

For quick local/agent preflight:

```bash
./scripts/verify.sh fast
```

`fast` runs the non-HIL test suite and skips only coverage reporting.

For required final validation before completion:

```bash
./scripts/verify.sh full
```

## Install the CLI

### Set up with Codex or Claude Code

After cloning this repository, open it in Codex or Claude Code and paste:

```text
Install DebugOracle globally for this user. Read the project instructions and
README.md first.
Use the supported installer. Before running it, summarize every optional
installation component. The 0.2.0 supported installer provides only the base
`pypdf` profile because the optional Docling and semantic dependency/model
license audits are incomplete. Proceed with required routine per-user setup
without asking; ask only before privileged or
system-wide changes, destructive actions, project-file changes, or an explicit
PEP 668 override. Confirm when
`dbgoracle --version` works.
```

### Connect a firmware project

Open your **firmware project** in a new Codex or Claude Code session, then paste:

```text
Initialise this workspace completely for DebugOracle. Inspect the existing
firmware, build outputs, Cortex-Debug/OpenOCD configuration, PDFs under
docs/vendor/, and an SVD under .dbgoracle/. Initialise every capability whose
inputs are unambiguous, including workspace setup and docs ingestion. Do not
guess missing board settings; tell me the exact missing file and destination.
```

For predictable automatic discovery, copy your local inputs here before asking
the agent:

```text
your-firmware-project/
├── docs/vendor/          # reference manuals and datasheets (PDF)
└── .dbgoracle/           # exactly one default <device>.svd
```

Then the agent can run the non-interactive golden path directly:

```bash
dbgoracle init-workspace --workspace-root . --auto --yes --format json
```

The command initializes every capability whose local inputs are unambiguous and
returns structured next actions for the rest. Documentation-only initialization
requires no embedded toolchain, board, probe, executable, or OpenOCD setup; it
indexes eligible PDFs and returns `partial` (exit code 2) while the absent
hardware capabilities remain actionable. Multiple ELF, SVD, or Cortex-Debug
choices are reported rather than guessed.

Vendor PDFs, generated docs sidecars, and captured artifacts should remain
local and uncommitted. DebugOracle never downloads vendor documents during
automatic initialization; obtain any restricted manual yourself from its
official publisher and copy it to `docs/vendor/`.

Linux v1 ships a CLI-only installer path. It installs `dbgoracle`; it does not install `openocd`, VS Code, Cortex-Debug, or board-specific tooling.

Verified alpha environment: Ubuntu 24.04 LTS x86-64, Python 3.12, and `pipx`.
All other environments are unverified, including other Linux distributions,
architectures, and Python versions.

Prerequisites for the installer itself:

- Linux
- Python 3.10+
- `pipx`

Manifest-driven launcher path from a checkout:

```bash
./scripts/install/linux.sh
```

Docling, semantic, and combined profiles remain disabled for the 0.2.0 supported
installer because their dependency and model license audits are incomplete.
Use the supported base profile explicitly for non-interactive installs:

```bash
./scripts/install/linux.sh --docs-tools none
```

The optional package extras remain declared for downstream experimentation but
are outside the supported installer path. See `THIRD_PARTY_NOTICES.md` and the
dependency audit before selecting them manually.

Secondary local-dev path from a checkout:

```bash
pipx install .
```

The checkout launcher installs from the local repository source by passing a local package override to `install-cli`. The manifest is still used for release metadata checks.

If the installer succeeds but `dbgoracle` is not immediately on `PATH`, it offers one managed shell-profile update and also prints the exact line to add manually.

Embedded toolchain checks happen later during workspace setup and capture flows, not during install success.

### Uninstall the CLI

Linux uninstall path from a checkout:

```bash
./scripts/install/uninstall.sh
```

Optional flags:

```bash
./scripts/install/uninstall.sh --format json
./scripts/install/uninstall.sh --keep-path
./scripts/install/uninstall.sh --force-legacy-path-cleanup
```

Uninstall scope is intentionally narrow:

- removes the `debugoracle` pipx package
- prompts in interactive mode before removing bundled docs tooling from the same pipx environment
- removes installer-managed PATH profile lines when they are marker-owned
- leaves workspace artifacts (for example `.dbgoracle/` and docs sidecars) untouched

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
mkdir -p docs/vendor
cp /path/to/Reference_Manual.pdf docs/vendor/
dbgoracle docs ingest --workspace-root . --yes --no-interactive
dbgoracle docs search "USART baud rate register"
dbgoracle docs status
```

Key points:

- Default parser is `pypdf` (`pypdf` is installed with base dependencies).
- Optional Docling parsing and semantic search remain outside the 0.2.0 supported installer while their dependency and model license audits are incomplete.
- Preflight dependency check: `dbgoracle docs doctor`.
- If you run ingest without `--file`/`--folder`, DebugOracle discovers likely PDFs under `doc/` and `docs/` and requires `--yes` confirmation.
- In TTY mode, ingest can prompt for discovered-doc confirmation; use `--no-interactive` to disable prompts.
- Failed long ingests keep staging checkpoints and can resume compatible reruns.
- Sidecar artifacts are written next to each source as `<source>.dbgoracle-docs/`.

Full usage and troubleshooting:
[`docs/docs-ingestion.md`](docs/docs-ingestion.md)

### Bootstrap a workspace

If you are using an agent, the natural-language initialization request above is
the recommended entry point: the agent can resolve existing project settings,
run the automatic command below, ingest PDFs from `docs/vendor/`, and use
exactly one `.dbgoracle/<device>.svd`. It must report ambiguous or missing
hardware-specific inputs instead of guessing them.

```bash
dbgoracle init-workspace --workspace-root . --auto --yes --format json
```

`--yes` explicitly authorizes parsing discovered local PDFs. Omit it to inspect
the deterministic plan and receive the exact authorization action without
parsing those documents. The automatic mode performs no build, download,
network access, probe connection, or target interaction.

For a fully explicit hardware setup, provide each input yourself:

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
./dbgoracle run --detach --workspace-root . --port 60001 --output .dbgoracle/session.rtt
./dbgoracle fetch --workspace-root .
./dbgoracle report --workspace-root .
./dbgoracle stop --workspace-root .
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
