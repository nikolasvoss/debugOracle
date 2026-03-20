# DebugOracle PoC Definition

## Purpose

This proof of concept exists to verify one concrete product claim:

DebugOracle can turn one real STM32 debug stop into an evidence handoff that an
agent can use inside the same workspace.

This is a practical validation document, not an architecture document.

## PoC Outcome

The PoC is successful when DebugOracle ingests a bounded GDB/MI log from a real
`NUCLEO-L432KC` Cortex-Debug session, builds a snapshot, renders a useful
GDB-based report, and produces a prompt artifact that an agent in the same
workspace can use after a lightweight instruction such as "fetch the prompt from
dbgoracle".

## Environment

- Board: `NUCLEO-L432KC`
- Debug flow: Cortex-Debug with GDB/MI logging enabled
- Evidence source required for PoC: GDB/MI log
- RTT: optional, not required for success
- Firmware: any simple STM32 example program that produces a meaningful stop
  such as blinky, UART interrupt, or timer-based examples
- Stop type: any meaningful stop is acceptable

## Product Claim Under Test

DebugOracle is useful in a real STM32 workspace when:

- a developer captures one bounded debug stop with Cortex-Debug
- DebugOracle packages the resulting GDB evidence with `fetch`
- the user or agent can inspect that evidence with `report`
- the agent can take the `prompt` output and continue reasoning from it

## Canonical Workflow

Use one bounded debug session and keep the capture focused on a single stop.

1. Set up Cortex-Debug so it writes a GDB/MI log into the workspace.
2. Run the STM32 example on the `NUCLEO-L432KC`.
3. Stop at one meaningful point.
4. Refresh Call Stack, Registers, and Variables/Locals so the GDB log contains
   useful halt context.
5. End the debug session for that incident.
6. Confirm the GDB/MI log exists and is not empty.
7. Run `dbgoracle fetch`.
8. Run `dbgoracle report`.
9. Run `dbgoracle prompt --goal "Explain why the target stopped here"`.
10. Hand the resulting report or prompt output to the agent working in the same
    STM32 workspace.

For concrete setup details, use the existing Cortex-Debug example docs in
[`examples/cortex-debug/README.md`](../examples/cortex-debug/README.md) and the
top-level workflow in [`README.md`](../README.md).

## Pass Conditions

The PoC passes when all of the following are true:

- A real `NUCLEO-L432KC` debug session produces a bounded GDB/MI log. ✅
- `dbgoracle fetch` succeeds from that log. ✅
- `dbgoracle report` contains useful GDB stop information. ✅
- The report includes stop-context evidence such as stop reason, stack,
  registers, or locals, or an explicit warning when some context is missing. ✅
- `dbgoracle prompt` produces a handoff artifact that an agent can use in the
  same workspace. ✅
- Another engineer can reproduce the same flow with the same board and tooling
  from this documentation plus the existing setup docs.

## Fail Conditions

The PoC fails if any of the following are true:

- No meaningful GDB/MI log is produced.
- The workflow depends on hidden local knowledge not captured in the docs.
- `dbgoracle fetch` cannot build a snapshot from the session evidence.
- `dbgoracle report` is too thin to hand off because the session did not capture
  meaningful GDB halt information.
- The prompt cannot be produced or is not usable as an agent handoff artifact.

## In Scope

- Real hardware validation on `NUCLEO-L432KC` ✅
- Cortex-Debug based GDB/MI log capture ✅
- File-based evidence ingestion ✅
- `fetch`, `report`, and `prompt` ✅
- Agent use inside the same STM32 workspace ✅
- Basic documentation for the required VS Code setup ✅

## Out Of Scope

- Generic board support
- Non-STM32 targets
- MCP integration
- Live reads
- Debugger control or automation beyond the documented manual workflow
- Multi-halt correlation
- Source-code enrichment
- Fully automated flashing or session startup
- Secret scrubbing or security hardening

## Notes

- GDB is the only required source for this PoC.
- RTT may still be present in the workspace, but it is not part of the success
  bar.
- This PoC proves a usable GDB evidence workflow, not the full future
  architecture of DebugOracle.
