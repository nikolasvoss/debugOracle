# Cortex-Debug setup example

This folder contains a minimal template and runbook to make first-time capture fast.

## 1) Copy example launch configuration

Create or update:

- `.vscode/launch.json`

Using the template:

- [`launch.jsonc.example`](launch.jsonc.example)
- [`tasks.json.example`](tasks.json.example)

Only the MI/RTT output sections need to be accurate for DebugOracle:

- MI transcript output should write to `.dbgoracle/cortex-debug-shared-mi.log`
- RTT (optional) output should write to `.dbgoracle/session.rtt`
- If your Cortex-Debug version uses different MI/RTT key names, edit only the logging lines in this template and keep the rest unchanged.

## 2) Run a bounded capture

- Start your Cortex-Debug session.
- Ensure `.dbgoracle` exists before starting by using the `DebugOracle: prepare capture paths` task from `tasks.json.example`.
- Reproduce the fault until the stop point you want to investigate.
- Open/refresh **Call Stack**, **Registers**, and **Variables/Locals** after the stop.
- Stop debugging for that run so the MI file stays bounded to one incident.

Before calling `observe`, confirm MI data exists:

```bash
test -s .dbgoracle/cortex-debug-shared-mi.log && echo "MI log ready" || echo "MI log empty or missing"
```

## 3) Build and inspect evidence

```bash
./dbgoracle observe --gdb-mi .dbgoracle/cortex-debug-shared-mi.log --rtt .dbgoracle/session.rtt
./dbgoracle report --snapshot-file .dbgoracle/latest_snapshot.json
```

Then hand it to ChatGPT:

```bash
./dbgoracle prompt --snapshot-file .dbgoracle/latest_snapshot.json --goal "Explain why the target stopped here"
```

## Minimal validation checklist

- `observe` exits successfully and writes `.dbgoracle/latest_snapshot.json`.
- `report` includes:
  - stop reason
  - at least one stack frame
  - registers or locals data (or explicit warning if missing)
- If no RTT is configured, you should still get a valid report; RTT lines are optional.

## Notes

- Cortex-Debug launch JSON schemas vary slightly by extension/version; keep only the MI/RTT paths and shared-logging settings aligned with your installed version.
- If logs are stale, remove old `.dbgoracle/*` files before next run.
