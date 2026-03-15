# DebugOracle

DebugOracle is a passive embedded-debug evidence packager for ChatGPT. It reads a bounded GDB/MI transcript plus optional RTT logs, builds a reusable evidence bundle, and renders either a local evidence report or a ChatGPT-ready prompt.

## Default workflow

DebugOracle does not drive the probe or debugger. The intended v1 flow is:

1. Start a Cortex-Debug session with shared MI logging available.
2. Reproduce until the target reaches a meaningful stop.
3. Open or refresh Call Stack, Registers, and Variables or Locals so Cortex-Debug emits the context you want to keep.
4. Save RTT output to a text log if runtime breadcrumbs matter.
5. Build a reusable snapshot with `observe`.
6. Inspect it locally with `report`.
7. Hand the same snapshot to ChatGPT with `prompt`.

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
- Run one focused debug stop.
- Build once:

```bash
./dbgoracle observe --gdb-mi .dbgoracle/cortex-debug-shared-mi.log --rtt .dbgoracle/session.rtt
./dbgoracle report --snapshot-file .dbgoracle/latest_snapshot.json
./dbgoracle prompt --snapshot-file .dbgoracle/latest_snapshot.json --goal "Explain why the target stopped here"
```

Before running `observe`, verify the MI file is receiving output:

```bash
test -s .dbgoracle/cortex-debug-shared-mi.log && echo "MI log ready" || echo "MI log empty or missing"
```

What to configure in Cortex-Debug:

- MI log path should point to `.dbgoracle/cortex-debug-shared-mi.log`.
- RTT path should point to `.dbgoracle/session.rtt` if your session has RTT enabled.
- Keep captures bounded: stop at the event you care about and end the debug session to avoid mixing multiple stops.
- Refresh Call Stack, Registers, and Variables/Locals before capture so the latest stop has rich context.

Quick check after run:

- `observe` succeeds and writes `.dbgoracle/latest_snapshot.json`.
- `report` shows stop reason + frame + register/local context.
- `prompt` includes evidence sections you can paste into ChatGPT.

See full sample config and step-by-step checklist in [`examples/cortex-debug/README.md`](examples/cortex-debug/README.md).

Typical Cortex-Debug flow:

```bash
./dbgoracle observe --gdb-mi /path/to/cortex-debug-shared-mi.log --rtt /path/to/session.rtt
./dbgoracle report --snapshot-file .dbgoracle/latest_snapshot.json
./dbgoracle prompt --snapshot-file .dbgoracle/latest_snapshot.json --goal "Explain why the target stopped here"
```

Advanced or automation-oriented rendering:

```bash
./dbgoracle snapshot --snapshot-file .dbgoracle/latest_snapshot.json --format json
cat /path/to/cortex-debug-shared-mi.log | ./dbgoracle snapshot --gdb-mi-stream --format json
printf "*stopped,reason=\"breakpoint-hit\",...\\n^done,register-values=[...]" | ./dbgoracle snapshot --gdb-mi - --format json
```

`--gdb-mi-stream` reads stdin until EOF. It is a bounded stdin capture mode, not a live `tail -f` follow mode.

## When raw JSON is useful

- Automation or scripting against the evidence bundle
- Re-rendering a saved snapshot without re-reading the original logs
- Attaching a machine-readable artifact to an issue or test case

Raw JSON is not required for the everyday `observe -> report -> prompt` workflow.

## Notes and boundaries

- v1 is read-only and does not call an LLM.
- `prompt` produces text or Markdown that you can paste into ChatGPT.
- If the MI log only contains `*stopped` without follow-up stack, register, or local queries, the snapshot is valid but thinner.
- If the MI log spans several stops, DebugOracle packages the latest stop-context it finds. Keep captures tight and per-stop when possible.
- RTT is optional. Missing RTT weakens the bundle but does not fail the run.
- MI and RTT inputs are treated as untrusted text. v1 does not guarantee redaction or secret scrubbing.
- Source-code enrichment and agentic capabilities are placeholders in this version.
