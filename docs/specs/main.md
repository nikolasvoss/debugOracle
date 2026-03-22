# main

- Module: `main`
- Code Path: `debugoracle/cli/main.py`
- Public Entrypoints: `main`, `build_parser`
- Last Updated: `2026-03-22`

# SPEC: DebugOracle CLI Parser And Dispatch

## Purpose

Own the top-level CLI parser, shared argument groups, and command dispatch wiring.

## Responsibilities

- Define the `dbgoracle` argparse surface.
- Keep command parsing easy to navigate by grouping behavior into command modules.
- Route parsed commands into the corresponding CLI command module without adding product logic.

## Command Routing

- `status`, `capture-rtt` -> `debugoracle/cli/commands/status_capture.py`
- `run`, `stop` -> `debugoracle/cli/commands/run_stop.py`
- `fetch`, `report` -> `debugoracle/cli/commands/evidence.py`
- `observe`, `snapshot`, and `prompt` are not exposed on the public CLI surface.

## Constraints

- Preserve the compatibility entrypoint exported by `debugoracle/cli/__init__.py`.
- Keep parser-only concerns here; avoid moving evidence shaping or policy logic back into dispatch.

## Report Inspect Flags

The parser owns the `report` inspect-mode surface after snapshot resolution has already been established:

- `--vars [NAME ...]`
- `--gdb`
- `--rtt`
- `--verbose`
- `--tail N`

Dispatch should pass these parsed flags through to the evidence command module without
interpreting the underlying evidence model in `main.py`.

Parser constraints:

- `--tail` must be a hard-positive integer
- `--tail` is valid only when a stream-bearing section is requested
- inspect flags may be combined, in which case `report` emits one compact JSON object containing
  only the requested sections

## Register Inspection Flags

The parser owns snapshot-only register inspection flags for `report`:

- `--regs-list [PERIPHERAL]`
- `--regs [SELECTOR ...]` where selectors are `PERIPHERAL` or `PERIPHERAL:REGISTER`

Dispatch treats these as snapshot filters only.

## Fetch SVD Contract

- `fetch --svd-file <file>` is the capture surface for SVD-backed peripheral register values.
- The current implementation expects a recent halted stop in the GDB/MI log and uses the default OpenOCD control endpoint for safe peripheral register reads.
- `fetch` keeps the SVD request on the capture side; `report` remains inspection-only.
