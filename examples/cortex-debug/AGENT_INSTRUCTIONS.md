# DebugOracle Agent Runbook

Goal:
- Help an agent use DebugOracle correctly inside a Cortex-Debug/OpenOCD STM32
  workspace.
- Optimize for the shortest correct workflow: bootstrap if needed, inspect
  current trust and evidence, then capture only when required.

## Product boundary

DebugOracle is evidence-first.

- It inspects workspace artifacts and renders debug evidence.
- It does not control the debugger.
- It does not write to target memory.
- It does not read the workspace source tree for you.

The agent must combine DebugOracle evidence with source and workspace context
when answering the user.

## Required self-discovery rule

Do not guess DebugOracle flags, output modes, or command behavior.

If the user asks for an unfamiliar command, a different rendering mode, or a
transport detail, inspect CLI help first:

```bash
dbgoracle --help
dbgoracle <command> --help
```

Use only the public CLI surface shown in help:

- `init-workspace`
- `status`
- `capture-rtt`
- `run`
- `stop`
- `find-tcl-port`
- `fetch`
- `report`

Do not invent or rely on non-public commands such as `observe` or `snapshot`.

## Fast path

Use this default decision loop unless the user asks for something narrower.

1. If the workspace is not set up yet, bootstrap it:

```bash
dbgoracle init-workspace --workspace-root . --executable path/to/firmware.elf --attach --openocd-config interface/stlink.cfg --openocd-config target/stm32l4x.cfg
```

2. Check current artifact health first:

```bash
dbgoracle status --workspace-root .
```

3. If a usable snapshot already exists, inspect it without rebuilding:

```bash
dbgoracle report --workspace-root .
```

4. If no usable snapshot exists but raw evidence exists, build one:

```bash
dbgoracle fetch --workspace-root .
```

5. After a snapshot exists, use the narrowest report surface that answers the
   request.

Core rule:

- `fetch` is capture-only.
- `report` is inspection-only.
- Default `report` output is intentionally short and trust-first.

## Which requests map to DebugOracle?

Treat requests like these as DebugOracle tasks:

- "summarize the latest dbgoracle evidence"
- "get the debug report"
- "show me the detailed embedded evidence"
- "show me the register catalog"
- "show me stored peripheral register values"
- "use dbgoracle on this workspace"

Prefer the smallest successful path that produces the requested artifact.

## Command model

1. Workspace bootstrap
   - `dbgoracle init-workspace`
2. Transport and workspace health
   - `dbgoracle status`
   - `dbgoracle capture-rtt`
   - `dbgoracle run`
   - `dbgoracle stop`
   - `dbgoracle find-tcl-port`
3. Evidence capture and stabilization
   - `dbgoracle fetch`
4. Evidence rendering and inspection
   - `dbgoracle report`

## Command contract

### `init-workspace`

Use when the workspace is missing supported `.dbgoracle` or `.vscode` setup.

- It is a setup helper, not an evidence command.
- It requires one or more `--openocd-config` values for the generated Cortex-Debug launch.
- `--attach` is the explicit mode for existing workspaces. In that mode, DebugOracle emits merge-ready fragments for the coding agent instead of silently editing user-owned VS Code files.
- If that flag is missing, the CLI now explains what `interface/*.cfg` and `target/*.cfg` mean and shows a corrected example command.
- It refuses to overwrite user-owned VS Code config by default.
- It can store a workspace-default SVD path for later `fetch` use.

### `status`

Use first when you need to know what evidence exists and what to do next.

- It is read-only.
- It reports current artifact health and transport state.
- It also derives golden-path readiness from current workspace/runtime truth: `setup_missing`, `prepared`, `live`, or `degraded`.
- It should be the first command before assuming capture is required.

### `capture-rtt`

Use only for one-shot raw RTT capture when the user specifically needs that
surface.

- It captures RTT to a file.
- It does not build a snapshot.

### `run` and `stop`

Use when DebugOracle should manage RTT capture for the workspace lifecycle.

```bash
dbgoracle run --detach --workspace-root .
# later
dbgoracle stop --workspace-root .
```

- `run` manages RTT capture in foreground or detached mode.
- `stop` stops only managed DebugOracle RTT runs.

### `fetch`

Use when raw evidence exists and a snapshot must be built or refreshed.

- `fetch` builds a stable snapshot from raw evidence.
- It never treats an existing snapshot as the primary source.
- It can succeed with degraded evidence if at least one selected raw source is
  available.
- It may use a workspace-default SVD from `.vscode/settings.json` when no
  explicit `--svd-file` is supplied.
- It may opportunistically use exactly one `.dbgoracle/*.svd` file when that is
  unambiguous. If discovery is ambiguous or live capture fails, it falls back
  to non-SVD capture with a clear notice.

### `report`

Use when you want to inspect a saved snapshot.

- `report` is snapshot-only.
- It does not rebuild from raw evidence.
- Default output is short and starts with a trust verdict.
- If trust is unsafe, default output stays short unless the user explicitly
  requests broader inspection, for example with `--allow-unsafe`.

Common inspection surfaces:

```bash
dbgoracle report --workspace-root .
dbgoracle report --workspace-root . --verbose
dbgoracle report --workspace-root . --vars
dbgoracle report --workspace-root . --vars myVar anotherVar
dbgoracle report --workspace-root . --gdb
dbgoracle report --workspace-root . --gdb --tail 100
dbgoracle report --workspace-root . --rtt
dbgoracle report --workspace-root . --rtt --tail 100
dbgoracle report --workspace-root . --regs-list
dbgoracle report --workspace-root . --regs-list GPIOA
dbgoracle report --workspace-root . --regs RCC
dbgoracle report --workspace-root . --regs GPIOA:MODER RCC:AHB2ENR
```

## Preferred workflow by situation

When `status` reports `prepared`, the next human step is to start `DebugOracle: Attach STM32` in VS Code and keep it running. `live` requires multiple runtime signals; one weak clue is not enough.

For "get the debug report":

```bash
dbgoracle status --workspace-root .
dbgoracle report --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root .
```

For "show me the detailed embedded evidence":

```bash
dbgoracle status --workspace-root .
dbgoracle report --workspace-root . --verbose
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root . --verbose
```

For "summarize the latest dbgoracle evidence":

```bash
dbgoracle status --workspace-root .
dbgoracle report --workspace-root .
dbgoracle fetch --workspace-root .   # only if no usable snapshot exists
dbgoracle report --workspace-root .
```

## Advanced: peripheral register capture

Use SVD-backed peripheral capture only when the user actually wants peripheral
register evidence.

Key rules:

- `--svd-file` is valid on `fetch`, not on `report`.
- Live peripheral capture is an explicit opt-in when `fetch` resolves an SVD.
- It requires a recent halted stop in the GDB/MI log.
- It uses the OpenOCD Tcl control endpoint for safe reads.
- The RTT port is not the OpenOCD Tcl port.
- `report --regs-list` is the discovery surface.
- `report --regs` is the stored-value and status surface.

Common forms:

```bash
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd --openocd-tcl-port 50001
dbgoracle fetch --workspace-root . --svd-file path/to/device.svd --openocd-tcl-host 127.0.0.1 --openocd-tcl-port 50001
```

After capture:

```bash
dbgoracle report --workspace-root . --regs-list
dbgoracle report --workspace-root . --regs RCC
```

If `fetch` has no explicit `--svd-file`, SVD resolution order is:

1. workspace-default `debugoracle.svdFile` from `.vscode/settings.json`
2. exactly one `.dbgoracle/*.svd` candidate
3. fallback to plain non-SVD capture

Do not imply that register capture happened unless `fetch` clearly resolved an
SVD and the resulting snapshot contains register data.

## Fastest way to find the Tcl port

Preferred path for agents and terminal workflows:

1. Start the current Cortex-Debug session.
2. Run the subcommand from the workspace root:

```bash
dbgoracle find-tcl-port --workspace-root . --print-fetch
```

The subcommand inspects the live `openocd` process, prints the active Tcl port,
and prints a ready-to-run `dbgoracle fetch ... --openocd-tcl-port <port>`
command when it can also resolve an SVD file.

If you only need the number, omit `--print-fetch`:

```bash
dbgoracle find-tcl-port --workspace-root .
```

The subcommand prefers the `openocd` process whose working directory matches
the workspace root. It avoids depending on the shared GDB/MI log because that log
may begin after startup traffic and may not include the OpenOCD launch line.

Manual fallback if the subcommand cannot find a single active session:

1. Open the Debug Console with `showDevDebugOutput: "raw"` enabled.
2. Search for `tcl_port` in the current session output.
3. Use the printed value for `--openocd-tcl-port`.

Example:

```text
... -c "gdb_port 50000" -c "tcl_port 50001" -c "telnet_port 50002" ...
```

In that session, use `50001` for `--openocd-tcl-port`.

## Raw evidence expectations

- GDB/MI log is the main evidence source for stop analysis.
- RTT is optional context.
- `fetch` can build a degraded snapshot if only one selected raw source exists.
- `report` does not read raw evidence directly.

## Failure handling

Stop and report the issue if any of the following are true:

- no snapshot exists and no usable raw evidence can be found
- `report` cannot resolve a snapshot
- the session did not capture meaningful halt context, so the report is thin
- the user expects debugger control, breakpoint management, or target writes
- `fetch --svd-file` is requested but the workspace does not have a recent
  halted stop or cannot reach the OpenOCD Tcl endpoint

Call out these silent-failure risks explicitly:

- a stale snapshot may exist but still deserve caution or refresh
- `fetch` may fall back to non-SVD capture if SVD resolution is ambiguous or
  live capture fails
- `--openocd-tcl-host` and `--openocd-tcl-port` do not matter when no SVD is
  resolved
- a short default unsafe report is not the same as full evidence absence

## Troubleshooting guidance

- If `report` says no snapshot is available, point the user to
  `dbgoracle fetch --workspace-root .`.
- If `status` shows setup is missing, point the user to
  `dbgoracle init-workspace --workspace-root . --executable path/to/firmware.elf --openocd-config interface/stlink.cfg --openocd-config target/stm32l4x.cfg`.
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
