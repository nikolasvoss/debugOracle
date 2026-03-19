# Cortex-Debug setup example

This folder contains an STM32/OpenOCD-flavored example plus a runbook to make
first-time capture fast.

## 1) Copy example launch configuration

For offline agent-oriented verification, see [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md).

Create or update:

- `.vscode/launch.json`

Using the template:

- [`launch.jsonc.example`](launch.jsonc.example)
- [`tasks.json.example`](tasks.json.example)

DebugOracle only requires the MI output path plus an OpenOCD RTT TCP endpoint,
but this example is not a generic Cortex-Debug template. Expect to edit the
target-specific fields before using it on another project:

- MI transcript output should write to `./cortex-debug-shared-mi.log` or `.dbgoracle/cortex-debug-shared-mi.log`
- RTT should be captured by `./dbgoracle run` into `.dbgoracle/session.rtt`
- The launch config must still enable RTT in your installed Cortex-Debug/OpenOCD
  setup so an RTT TCP server is actually exposed.
- If your Cortex-Debug version uses different MI/RTT key names, update only the
  logging lines.
- `serverpath` in the sample is optional and commented out by default.
  This repo does **not** ship `.vscode/openocd-wrapper.sh` (it is your local
  advanced setup choice only).
- If you are not using this exact STM32/OpenOCD setup, also update
  `configFiles`, `executable`, `gdbPath`, and `runToEntryPoint`.

## 1.5) Quick preflight

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

## 2) Run a bounded capture

- Ensure `.dbgoracle` exists before starting by using the `DebugOracle: Prelaunch` task from `tasks.json.example`.
- `DebugOracle: Prelaunch` runs `dbgoracle run --detach` so RTT capture can begin before the debug session reaches the first stop.
- `DebugOracle: Stop RTT run` runs automatically as `postDebugTask`, and you can also run it manually.
- If you are not using tasks, use this lifecycle directly:

```bash
./dbgoracle run --detach --workspace-root . --port 60001 --output .dbgoracle/session.rtt
# later, after your debug session:
./dbgoracle stop --workspace-root .
```

- Start your Cortex-Debug session.
- Use the TCP port that Cortex-Debug/OpenOCD prints for the active RTT channel. Channel `0` is often exposed on `60001`.
- Keep `tasks.json.example` aligned with the actual RTT TCP port for your
  session. If OpenOCD/Cortex-Debug exposes a different port, update
  `DebugOracle: Start RTT run` to match it.
- Use only one RTT consumer at a time. Do not run `uScope` or a second RTT terminal while `dbgoracle run` is attached.
- Reproduce the fault until the stop point you want to investigate.
- Open/refresh **Call Stack**, **Registers**, and **Variables/Locals** after the stop.
- Stop debugging for that run so the MI file stays bounded to one incident.

Before calling `observe`, confirm MI data exists:

```bash
test -s cortex-debug-shared-mi.log && echo "MI log ready" || test -s .dbgoracle/cortex-debug-shared-mi.log && echo "MI log ready" || echo "MI log empty or missing"
test -s session.rtt && echo "RTT log has data" || test -s .dbgoracle/session.rtt && echo "RTT log has data" || echo "RTT log empty or not enabled"
test -f session.rtt.state.json && echo "RTT capture state present" || test -f .dbgoracle/session.rtt.state.json && echo "RTT capture state present" || echo "RTT capture helper not attached"
```
MI data is required for every capture. Reset logs between runs with `Prepare debug logs`
to avoid stale evidence.

## 3) Build and inspect evidence

```bash
./dbgoracle observe
./dbgoracle report
```

Then hand it to ChatGPT:

```bash
./dbgoracle prompt --goal "Explain why the target stopped here"
```

## Minimal validation checklist

- `observe` exits successfully and writes `latest_snapshot.json` in the detected artifact folder
  (workspace root or `.dbgoracle`).
- `status` shows an `RTT Capture` section with the RTT transport state if you used `run`.
- `report` includes:
  - stop reason
  - at least one stack frame
  - registers or locals data (or explicit warning if missing)
- If no RTT is configured, you should still get a valid report; RTT lines are optional.

## Notes

- Cortex-Debug launch JSON schemas vary slightly by extension/version; keep only the MI/RTT paths and shared-logging settings aligned with your installed version.
- Treat Cortex-Debug `rttConfig.logFile` as best-effort only. The supported robust path is `./dbgoracle run`.
- If the RTT file stays empty, inspect `.dbgoracle/session.rtt.state.json` or run `./dbgoracle status` to see whether capture connected, stayed idle, or hit an error.
- If the RTT file stays empty from the start, the two most likely causes are:
  - the launch configuration did not enable RTT, so no RTT TCP server came up
  - the `dbgoracle run --port ...` value does not match the actual RTT TCP port
    printed by Cortex-Debug/OpenOCD
- If a debug session ends unexpectedly, run `./dbgoracle stop --workspace-root .` to clean up detached runtime metadata.
- If logs are stale, remove old `.dbgoracle/*` files before next run.
- For security, treat MI/RTT logs as potentially sensitive traces (register values,
  call frames, and firmware-related strings).

## Which command when?

- Incident capture (recommended): run `DebugOracle: Prelaunch`, debug one incident, then let `postDebugTask` call `DebugOracle: Stop RTT run`.
- Manual workflow without VS Code: run `./dbgoracle run --detach ...` before debugging and `./dbgoracle stop --workspace-root .` after.
- Continuous multi-session capture: add `--append` to `run --detach` and rotate or reset `.dbgoracle/session.rtt` between investigations.

## Expected run/stop messages

- `Started detached RTT run (pid ... )` means background capture is active.
- `Detached RTT run already active` means a prior managed session is still running.
- `Warning: Detached RTT run pid ... is not running. Cleaning up stale metadata.` means a stale runtime file was found and repaired.
- `RTT run stopped because the RTT server closed the connection.` means capture auto-stopped without VS Code because the transport ended.
