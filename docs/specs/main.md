# main

- Module: `main`
- Code Path: `debugoracle/cli/main.py`
- Public Entrypoints: `main`, `build_parser`
- Last Updated: `2026-03-19`

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

## Shared Variable Selectors

The parser owns one shared variable-evidence selector surface for `snapshot`, `report`, and
`prompt`:

- `--var-scope local|watchpoint|unknown|all`
- repeatable `--var-name`
- `--var-detail compact|full`

Dispatch should pass these parsed selectors through to the evidence command module without
interpreting the underlying evidence model in `main.py`.
