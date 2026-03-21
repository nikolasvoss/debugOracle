# DebugOracle Agent Runbook

Goal:
- Help an agent use DebugOracle correctly inside a Cortex-Debug/OpenOCD STM32
  workspace.
- Keep the workflow aligned with the current CLI model:
  transport health and RTT capture, raw-evidence fetch, and snapshot-only
  inspection.

## Current product boundary

- DebugOracle is evidence-first.
- It does not control the debugger.
- It does not write to target memory.
- It does not read the workspace source tree for you.
- The agent should combine DebugOracle evidence with source and workspace
  context when answering the user.

## Interpret these requests as DebugOracle tasks

- "fetch the prompt from dbgoracle"
- "get the debug report"
- "show me the detailed embedded evidence"
- "show me the register catalog"
- "show me stored peripheral register values"
- "use dbgoracle on this workspace"

The agent should prefer the smallest successful path that produces the
requested artifact.

## Required self-discovery rule

Do not guess DebugOracle flags, output modes, or command behavior.

When the user asks for a different rendering mode, an unfamiliar command, or a
transport workflow detail, inspect the CLI help first:

```bash
dbgoracle --help
dbgoracle <command> --help
```

Use only the public CLI surface shown in help:

- `status`
- `capture-rtt`
- `run`
- `stop`
- `fetch`
- `report`
- `prompt`

Do not invent or rely on non-public commands such as `observe` or `snapshot`.

## Command model

1. Transport and workspace health
   - `dbgoracle status`
   - `dbgoracle capture-rtt`
   - `dbgoracle run`
   - `dbgoracle stop`
2. Evidence capture and stabilization
   - `dbgoracle fetch`
3. Evidence rendering and packaging
   - `dbgoracle report`
   - `dbgoracle prompt`

Key rule:

- `fetch` is raw-evidence capture only.
- `report` is snapshot-only inspection.
- `prompt` is snapshot-only packaging.
- Default `report` output is intentionally short. Use inspect flags for detail.

## Command decision path

1. Start with workspace health:

```bash
dbgoracle status --workspace-root .
```

2. If a usable snapshot already exists, do not rebuild it just to inspect:
   - use `dbgoracle report --workspace-root .`
   - use `dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"`

3. If no snapshot exists but raw evidence exists, build one:
   - use `dbgoracle fetch --workspace-root .`

4. After a snapshot exists, choose the narrowest inspection surface:
   - default summary:

```bash
dbgoracle report --workspace-root .
```

   - variables:

```bash
dbgoracle report --workspace-root . --vars
dbgoracle report --workspace-root . --vars myVar anotherVar
```

   - GDB evidence:

```bash
dbgoracle report --workspace-root . --gdb
dbgoracle report --workspace-root . --gdb --tail 100
```

   - RTT evidence:

```bash
dbgoracle report --workspace-root . --rtt
dbgoracle report --workspace-root . --rtt --tail 100
```

   - register catalog discovery:

```bash
dbgoracle report --workspace-root . --regs-list
dbgoracle report --workspace-root . --regs-list GPIOA
```

   - stored register values and statuses:

```bash
dbgoracle report --workspace-root . --regs RCC
dbgoracle report --workspace-root . --regs GPIOA:MODER RCC:AHB2ENR
```

   - combined structured output:

```bash
dbgoracle report --workspace-root . --gdb --vars --regs RCC
dbgoracle report --workspace-root . --verbose
```

5. If the user asks for an agent handoff artifact rather than a human report:

```bash
dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"
```

6. If neither a snapshot nor usable raw evidence exists, report that required
   debug evidence is missing.

## Raw evidence expectations

- GDB/MI log is the main evidence source for stop analysis.
- RTT is optional.
- `fetch` can build a degraded snapshot if only one selected raw source exists.
- `report` and `prompt` do not read raw evidence directly.

## Optional SVD-backed peripheral capture

Use SVD-backed peripheral capture only when the user actually wants peripheral
register evidence. A plain `fetch` may opportunistically use exactly one
workspace `.dbgoracle/*.svd` file when it can do so unambiguously; otherwise it
falls back to non-SVD capture with a clear notice.

Capture step with the common default Tcl port:

```bash
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd
```

Capture step when the current debug session exposes a remapped Tcl port:

```bash
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd --openocd-tcl-port 50001
```

Host and port override together:

```bash
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd --openocd-tcl-host 127.0.0.1 --openocd-tcl-port 50001
```

Guardrails:

- `--svd-file` is valid on `fetch`, not on `report`.
- `--openocd-tcl-host` and `--openocd-tcl-port` are used only when an explicit or auto-discovered SVD is available. Otherwise `fetch` falls back to non-SVD capture and says so clearly.
- This is an explicit opt-in to halted live peripheral capture.
- It requires a recent halted stop in the GDB/MI log.
- It uses the OpenOCD Tcl control endpoint for safe reads.
- The RTT port is not the OpenOCD Tcl port.
- Default `report` output stays short; use `--regs-list` and `--regs` to inspect
  the captured register catalog and stored values.

## Fastest way to find the Tcl port

1. Start the current Cortex-Debug session with raw server output enabled.
2. Open the Debug Console or the shared GDB/MI log.
3. Search for `tcl_port`.
4. Use the printed value if it differs from `6666`.

Example pattern:

```text
... -c "gdb_port 50000" -c "tcl_port 50001" -c "telnet_port 50002" ...
```

In that session, use `50001` for `--openocd-tcl-port`.

## Preferred verification flows

For "get the debug report":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root .
```

For "show me the detailed embedded evidence":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root . --verbose
```

For "show me the register catalog":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd --openocd-tcl-port 50001   # only if the snapshot does not already contain register data
dbgoracle report --workspace-root . --regs-list
```

For "show me stored peripheral register values":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd --openocd-tcl-port 50001   # only if the snapshot does not already contain register data
dbgoracle report --workspace-root . --regs RCC
```

For "fetch the prompt from dbgoracle":

```bash
dbgoracle status --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"
```

## Failure handling

Stop and report the issue if any of the following are true:

- no snapshot exists and no usable raw evidence can be found
- `report` or `prompt` cannot resolve a snapshot
- the session did not capture meaningful halt context, so the report is thin
- the user expects debugger control, breakpoint management, or target writes
- `fetch --svd-file` is requested but the workspace does not have a recent
  halted stop or cannot reach the OpenOCD Tcl endpoint

## Troubleshooting guidance

- If `report` or `prompt` says no snapshot is available, point the user to
  `dbgoracle fetch --workspace-root .`.
- If the stop summary is thin, suggest refreshing Call Stack, Registers, and
  Variables/Locals before ending the debug session and then recapturing.
- If RTT is empty or missing, use `dbgoracle status --workspace-root .` to check
  transport state before assuming the incident had no stream output.
- If the user needs RTT capture managed by DebugOracle, prefer:

```bash
dbgoracle run --detach --workspace-root .
# later
dbgoracle stop --workspace-root .
```

- If the user needs one-shot RTT capture to a specific file, prefer
  `dbgoracle capture-rtt --help` first and then use the supported flags from
  help output.
- If `fetch --svd-file` fails with connection refused, confirm you found the
  current session's `tcl_port` rather than reusing an old port or the RTT port.
- If `fetch --svd-file` behaves like a stream instead of a control connection,
  you are probably pointing at RTT instead of the Tcl endpoint.
