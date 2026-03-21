# Cortex-Debug setup example

This folder contains an STM32/OpenOCD-flavored example plus a runbook to make
first-time capture fast.

## 1) Copy example launch configuration

For offline agent-oriented verification, see [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md).

Create or update:

- `.vscode/launch.json`

Using the template:

- [`settings.json.example`](settings.json.example)
- [`launch.jsonc.example`](launch.jsonc.example)
- [`tasks.json.example`](tasks.json.example)

DebugOracle always requires the MI output path. RTT remains optional for stream
capture, and live peripheral capture via `fetch --svd-file ...` can also use
`--openocd-tcl-host` and `--openocd-tcl-port` when the debug session exposes a
non-default Tcl endpoint. This example is not a generic Cortex-Debug template.
Expect to edit the target-specific fields before using it on another project:

- MI transcript output should write to `./cortex-debug-shared-mi.log` or `.dbgoracle/cortex-debug-shared-mi.log`
- RTT should be captured by `dbgoracle run` into `.dbgoracle/session.rtt`
- Live peripheral capture via `dbgoracle fetch --svd-file <file>` needs the
  OpenOCD Tcl control port in addition to MI data
- If your Cortex-Debug version uses different MI or RTT key names, update only the
  logging lines
- `serverpath` in the sample is optional and commented out by default
- If you are not using this exact STM32/OpenOCD setup, also update
  `configFiles`, `executable`, `gdbPath`, and `runToEntryPoint`

## Single place for project values

Copy [`settings.json.example`](settings.json.example) to `.vscode/settings.json` and keep your project-specific values there.

The example launch and task files read these settings so the important values live in one place:

- `debugoracle.executable`: path to your ELF
- `debugoracle.miLogPath`: shared GDB/MI log path
- `debugoracle.rttLogPath`: RTT capture path
- `debugoracle.rttStatePath`: RTT state sidecar path
- `debugoracle.rttLaunchLogPath`: helper launch log path
- `debugoracle.rttPort`: RTT port used by `dbgoracle run`

These are the stable project values. The OpenOCD Tcl port is intentionally not
stored here because Cortex-Debug may remap it per session. Discover it from the
active debug log when you use `fetch --svd-file`.

## Port map

Treat the OpenOCD ports as three separate things:

- `gdb_port`: used by GDB only
- `tcl_port`: used by `dbgoracle fetch --svd-file ...` for live peripheral reads
- RTT port: used by `dbgoracle run` and `monitor rtt server start <port> <channel>`

Do not reuse the RTT port for live peripheral capture. If RTT is on `60001`,
that does not tell you anything about the Tcl port.

## Fastest way to find the Tcl port

1. Set your stable project values in `.vscode/settings.json`.
2. Start your Cortex-Debug session with `showDevDebugOutput: "raw"` enabled.
3. Open the Debug Console or the shared GDB/MI log.
4. Search for `tcl_port`.

A real example looks like this:

```text
Launching gdb-server: openocd -c "gdb_port 50000" -c "tcl_port 50001" -c "telnet_port 50002" -s /home/niko/Dokumente/Bastelei/stm32_1 -f /home/niko/.vscode/extensions/marus25.cortex-debug-1.12.1/support/openocd-helpers.tcl -f interface/stlink.cfg -f target/stm32l4x.cfg -c "adapter speed 4000"
```

In that session, the Tcl port is `50001`.

If you do not see any `tcl_port` entry, your current session is not giving you
a usable Tcl port yet. In that case, stop and fix the debug launch first.

## What to do with the number

Once you have the port number, use this happy path:

1. Verify the port is reachable.
2. Run `fetch --svd-file` with that port.
3. Optionally export it for repeated use in the same shell.

Verify reachability:

```bash
python3 - <<'PY'
import socket
port = 50001
with socket.socket() as s:
    s.settimeout(0.5)
    s.connect(("127.0.0.1", port))
print(f"127.0.0.1:{port} is reachable")
PY
```

Run `fetch --svd-file` with the discovered port:

```bash
dbgoracle fetch --workspace-root . --svd-file .dbgoracle/STM32L432.svd --openocd-tcl-port 50001
```

If you also need to override the Tcl host:

```bash
dbgoracle fetch --workspace-root . --svd-file .dbgoracle/STM32L432.svd --openocd-tcl-host 127.0.0.1 --openocd-tcl-port 50001
```

`6666` is only the common OpenOCD default. If your debug session prints a
remapped port like `50001`, use the printed value.

## Quick preflight

Before first capture, validate environment basics:

```bash
if ! command -v openocd >/dev/null 2>&1; then
  echo "openocd not found in PATH"
  exit 1
fi
openocd --version
test -f cortex-debug-shared-mi.log && echo "MI file path exists" || test -f .dbgoracle/cortex-debug-shared-mi.log && echo "MI file path exists" || echo "run Prepare debug logs first"
test -f .dbgoracle/session.rtt && echo "RTT file path exists" || echo "RTT log not present yet"
```

## Run a bounded capture

- Ensure `.dbgoracle` exists before starting by using the `DebugOracle: Prelaunch` task from `tasks.json.example`.
- `DebugOracle: Prelaunch` runs `dbgoracle run --detach` so RTT capture can begin before the debug session reaches the first stop.
- `DebugOracle: Stop RTT run` runs automatically as `postDebugTask`, and you can also run it manually.
- If you are not using tasks, use this lifecycle directly:

```bash
dbgoracle run --detach --workspace-root . --port 60001 --output .dbgoracle/session.rtt
# later, after your debug session:
dbgoracle stop --workspace-root .
```

- Start your Cortex-Debug session.
- Use the TCP port that Cortex-Debug or OpenOCD prints for the active RTT channel. Channel `0` is often exposed on `60001`.
- Keep `tasks.json.example` aligned with the actual RTT TCP port for your session.
- Use only one RTT consumer at a time. Do not run `uScope` or a second RTT terminal while `dbgoracle run` is attached.
- Reproduce the fault until the stop point you want to investigate.
- Open or refresh **Call Stack**, **Registers**, and **Variables/Locals** after the stop.
- Stop debugging for that run so the MI file stays bounded to one incident.

Before calling `fetch`, confirm MI data exists:

```bash
test -s cortex-debug-shared-mi.log && echo "MI log ready" || test -s .dbgoracle/cortex-debug-shared-mi.log && echo "MI log ready" || echo "MI log empty or missing"
test -s session.rtt && echo "RTT log has data" || test -s .dbgoracle/session.rtt && echo "RTT log has data" || echo "RTT log empty or not enabled"
test -f session.rtt.state.json && echo "RTT capture state present" || test -f .dbgoracle/session.rtt.state.json && echo "RTT capture state present" || echo "RTT capture helper not attached"
```

## Wrong port symptoms

- RTT port is reachable, but `fetch --svd-file` still fails or behaves strangely:
  you are probably pointing DebugOracle at the RTT stream instead of the Tcl
  control port.
- Tcl port is wrong or missing: `fetch --svd-file` fails with connection refused
  or a clear backend reachability error.
- The log shows an old port from a previous session: you are probably reading a
  stale MI or Debug Console log. Restart the debug session and search again.

## Build and inspect evidence

For the normal stop report:

```bash
dbgoracle fetch --workspace-root .
dbgoracle report --workspace-root .
```

For captured peripheral register inspection after `fetch --svd-file`:

```bash
dbgoracle report --workspace-root . --regs-list
dbgoracle report --workspace-root . --regs RCC
```

For an agent-ready handoff artifact:

```bash
dbgoracle prompt --workspace-root . --goal "Explain why the target stopped here"
```

## Minimal validation checklist

- Your `.vscode/settings.json` contains the normal project values in one place.
- You can point to the exact `tcl_port` line in the current debug session log.
- You can explain the difference between `gdb_port`, `tcl_port`, and the RTT port.
- You can verify the discovered Tcl port on `127.0.0.1:<port>`.
- You can run `dbgoracle fetch --workspace-root . --svd-file ... --openocd-tcl-port <port>`.
- You can inspect captured registers with `dbgoracle report --regs-list` or `dbgoracle report --regs ...`.
- `status` shows an `RTT Capture` section with the RTT transport state if you used `run`.

## Notes

- Cortex-Debug launch JSON schemas vary slightly by extension and version; keep only the MI and RTT paths plus shared logging aligned with your installed version.
- Treat Cortex-Debug `rttConfig.logFile` as best-effort only. The supported robust path is `dbgoracle run`.
- If the RTT file stays empty, inspect `.dbgoracle/session.rtt.state.json` or run `dbgoracle status` to see whether capture connected, stayed idle, or hit an error.
- If a debug session ends unexpectedly, run `dbgoracle stop --workspace-root .` to clean up detached runtime metadata.
- If logs are stale, remove old `.dbgoracle/*` files before the next run.
- For security, treat MI and RTT logs as potentially sensitive traces.

## Which command when?

- Incident capture: run `DebugOracle: Prelaunch`, debug one incident, then let `postDebugTask` call `DebugOracle: Stop RTT run`.
- Manual workflow without VS Code: run `dbgoracle run --detach ...` before debugging and `dbgoracle stop --workspace-root .` after.
- Continuous multi-session capture: add `--append` to `run --detach` and rotate or reset `.dbgoracle/session.rtt` between investigations.
