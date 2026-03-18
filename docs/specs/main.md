# main

- Module: `main`
- Code Path: `debugoracle/cli/main.py`
- Public Entrypoints: `main`, `build_parser`
- Last Updated: `2026-03-18`

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
- `observe`, `snapshot`, `report`, `prompt` -> `debugoracle/cli/commands/evidence.py`

## Constraints

- Preserve the compatibility entrypoint exported by `debugoracle/cli/__init__.py`.
- Keep parser-only concerns here; avoid moving evidence shaping or policy logic back into dispatch.
