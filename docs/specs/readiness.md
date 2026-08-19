# readiness

- Module: `readiness`
- Code Path: `debugoracle/readiness.py`
- Public Entrypoints: `collect_host_readiness`, `collect_workspace_plan`,
  `collect_session_plan`, `AutomaticInitInventory`,
  `plan_automatic_workspace_init`

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
- `collect_workspace_plan` also acquires one immutable automatic-initialization
  inventory. This additional inventory is intentionally absent from the legacy
  `WorkspacePlan.as_dict()` payload, whose schema version, fields, status, and
  command output remain unchanged.
- The automatic inventory reuses `discover_candidate_documents` for PDFs under
  `doc/` and `docs/`, ignores generated sidecar directories, inventories direct
  `.dbgoracle/*.svd` files, and reads bounded `.vscode/settings.json` and
  `.vscode/launch.json` mappings. Selected inventory files must be readable
  regular files contained by the resolved workspace. Raw `.cfg` candidates are
  evidence only and are never paired automatically.
- Candidate values are resolved, deduplicated, and sorted. Candidate classes
  are bounded independently; `truncated_candidate_classes` prevents the pure
  planner from selecting discovery results from an affected class while still
  allowing explicit or valid configured values for that class.
- `plan_automatic_workspace_init(inventory, ...)` is pure and performs no file,
  process, network, socket, debugger, or target I/O. Callers pass already
  validated absolute explicit paths. It applies `explicit` →
  `workspace_setting` → unique `workspace_discovery` precedence. OpenOCD values
  may additionally come from exactly one Cortex-Debug launch configuration and
  retain `cortex_debug_launch` provenance.
- Planner capabilities always appear as `documentation`, `debug_scaffold`, and
  `register_catalog`. Capability states are `complete`, `partial`, or
  `unavailable`; overall plan state is `complete`, `partial`, or `failed`.
  Inputs, ambiguities, evidence, and required actions use stable ordering, and
  the planner's `as_dict()` payload uses schema version `1`.
- `dbgoracle session doctor` validates local workspace files only; it must not
  import live OpenOCD transport code, open sockets, or contact a target.
  It accepts VS Code JSONC and validates Cortex-Debug config files, the selected
  executable, MI-log freshness, and local RTT listener evidence from `/proc`.
- JSON uses schema version `1`; output is ordered and no default command writes
  files.
