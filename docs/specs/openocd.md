# openocd

- Module: `openocd`
- Code Path: `debugoracle/openocd.py`
- Public Entrypoints: `OpenOcdCandidate`, `OpenOcdDiscoveryResult`, `OpenOcdReachabilityError`, `discover_workspace_openocd_session`, `discover_openocd_candidates`, `select_openocd_candidate`, `is_tcp_endpoint_reachable`, `parse_openocd_ports`, `looks_like_openocd_argv`
- Last Updated: `2026-03-23`

# SPEC: Shared OpenOCD Session Discovery

## Purpose

Provide one shared source of truth for discovering live OpenOCD processes, selecting the workspace-matching Tcl endpoint, and reporting structured recovery signals for fetch-time Tcl recovery.

## Responsibilities

- Discover OpenOCD processes from `/proc` first and `ps` as a fallback.
- Parse Tcl, GDB, and telnet ports from OpenOCD argv data.
- Prefer the OpenOCD session that matches the current workspace root.
- Report whether the selected endpoint is matched, unreachable, absent, ambiguous, or missing for a requested pid.
- Expose a typed reachability error surface used by SVD-backed live register capture.

## Contracts

- `discover_workspace_openocd_session()` returns a structured result instead of CLI text.
- `OpenOcdReachabilityError` is the typed signal for recoverable live-read connection failures.
- Discovery never starts or manages a debug session; a debug session must already be running for discovery to help.
- `find-tcl-port` and `fetch` must share this module instead of duplicating process-selection logic.
