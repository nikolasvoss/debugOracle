# readiness

- Module: `readiness`
- Code Path: `debugoracle/readiness.py`
- Public Entrypoints: `collect_host_readiness`, `collect_workspace_plan`, `collect_session_plan`

## Purpose

Provide deterministic, local-only readiness evidence before a Cortex-Debug
session starts.

## Contract

- `dbgoracle doctor host` reports host prerequisite evidence without installing
  software or probing hardware.
- `dbgoracle workspace plan` scans only the resolved workspace, does not follow
  symlinks, and reports candidates without selecting an ambiguous executable.
  Discovery is limited to root-level candidates and direct entries in `build/`,
  `out/`, `boards/`, and `config/`; it reports a blocked, truncated result at
  the deterministic entry limit.
- `dbgoracle session doctor` validates local workspace files only; it must not
  import live OpenOCD transport code, open sockets, or contact a target.
  It accepts VS Code JSONC and validates Cortex-Debug config files, the selected
  executable, MI-log freshness, and local RTT listener evidence from `/proc`.
- JSON uses schema version `1`; output is ordered and no default command writes
  files.
