# Agent Setup Readiness Implementation Plan

Status: Complete (read-only readiness slice)

## Purpose

Deliver the read-only foundation for a three-layer agent-assisted setup flow:
global DebugOracle CLI installation, per-machine debug-host readiness, and
per-workspace configuration diagnosis.

## Deferred Follow-up

Machine-readable attach merge plans, board profiles, structured remediation
actions, and automated application paths are intentionally deferred. They are
not part of this release.

## Task Link

[Agent Setup Readiness Task Spec](AGENT_SETUP_READINESS_TASK_SPEC.md)

## Files / Modules To Change

- `debugoracle/installer/`: retain the `pipx` global-install contract and expose
  only structured, safe remediation metadata required by the new guidance.
- `debugoracle/diagnostics.py` or a focused new diagnostics package: immutable
  diagnostic models, collectors, remediation metadata, and deterministic JSON
  rendering helpers.
- `debugoracle/cli/main.py`, `debugoracle/cli/commands/`: parser registration
  and command handlers for host, workspace, and session diagnostics.
- `debugoracle/cli/commands/init_workspace.py`: attach-mode merge-plan and diff
  rendering without changing overwrite policy.
- `docs/specs/`: module specs for every new public command/model and updates to
  `cli`, `main`, and `init_workspace` contracts.
- `README.md`, `docs/`: three-phase agent prompts, direct CLI fallbacks, and
  troubleshooting.
- `tests/`: diagnostics, CLI contracts, workspace fixtures, attach merge plans,
  and regressions for non-mutation and stable output.

## Architecture And State Flow

1. `dbgoracle doctor host` gathers local, read-only machine facts through small
   adapters. It emits an ordered `ReadinessReport` with a status, provenance,
   remedy, owner, and approval requirement per check. Remediation is a typed
   action identifier plus allowlisted arguments, never a command string from
   the machine or workspace.
2. `dbgoracle workspace plan --workspace-root PATH` reads only the target
   workspace. It emits candidates and unresolved choices; it does not write
   scaffold files or select a board/probe on insufficient evidence.
3. User or agent supplies confirmed inputs to the existing `init-workspace`
   flow. Attach mode returns both a display diff and merge-plan JSON, and still
   requires explicit application of any user-owned-file edit.
4. `dbgoracle session doctor --workspace-root PATH` validates the resulting
   local configuration and launch prerequisites. It does not start OpenOCD,
   open a socket to the probe, flash, reset, or halt the target.
5. Only after `ready` does the user start the existing Cortex-Debug launch.
   Session-status tooling then confirms MI-log freshness and evidence readiness.

## Implementation Steps

1. Create immutable readiness models and a versioned JSON schema. Define the
   five ordered status classes, provenance fields, remediation fields, ownership,
   and `requires_approval` semantics. Define a maintained remediation-action
   allowlist; command rendering is presentation-only and cannot consume command
   text from a board profile, process list, workspace file, or distro metadata.
2. Implement host collectors for Linux/tool/path/extension evidence. Use
   injected environment/process adapters so unit tests do not depend on a host.
   Start with supported facts; represent unsupported distro/probe cases as
   `blocked` or `needs_user_choice`, never a guessed install command. Bound
   every version/process probe by explicit argv, timeout, and output-size limit;
   redact process arguments in default output.
3. Add `doctor host` parser and text/JSON renderers. Keep stdout for report data
   and stderr for command errors.
4. Implement workspace candidate discovery and `workspace plan`. Reuse existing
   workspace resolution and static Cortex-Debug parsing where available; sort
   paths, report sources, require user input for ties, never follow directory
   symlinks, and reject candidates resolved outside the selected workspace.
5. Define a versioned project-local board-profile schema. Support only explicit,
   checked-in profiles in the first slice; do not ship heuristic board matching.
6. Extend `init-workspace --attach` with merge-plan JSON and a deterministic
   unified display diff. Preserve current marker/ownership checks and `--force`
   restrictions.
7. Implement `session doctor` as local static validation. Reuse current OpenOCD
   configuration parsers, but do not import `debugoracle.openocd`, live-session
   discovery, socket clients, or target transport code. Limit port-conflict
   reporting to local process/listener evidence that does not initiate a TCP
   connection. Add tests that fail on socket creation, OpenOCD subprocess
   launch, workspace writes, or target transport imports.
8. Add documentation for the three prompts and direct non-agent command paths.
   Explain that all host changes require user approval and that hardware probing
   is intentionally a separate future opt-in action.
9. Update module specs, registry, changelog/release documentation as warranted,
   then run all validation gates.

## Failure Handling

| Condition | Required behavior |
| --- | --- |
| Unsupported platform or distro | Report observed facts and a `blocked` status; no guessed package-manager command. |
| Missing host dependency | Report `needs_host_dependency`, exact evidence, approved command candidates, and `requires_approval: true`. |
| Several ELF/config/profile candidates | Report `needs_user_choice` with sorted candidates and provenance; do not pick one. |
| Existing user-owned VS Code JSON | Report `needs_workspace_merge`; generate a merge plan/diff; do not write it. |
| Invalid/missing local configuration | Report `blocked` with the exact path/key and remediation. |
| Running OpenOCD/port conflict | Report local process/port evidence; never kill a process automatically. |
| Any target-hardware check | Exclude it from default commands; require a later explicit opt-in command and clear target-interaction warning. |
| Workspace profile contains a command/remedy string | Treat it as opaque data, do not render or execute it, and report schema validation failure. |
| Candidate resolves through symlink outside workspace | Exclude it and report bounded provenance without reading the target. |
| Process output contains sensitive arguments | Redact by default; expose only an explicit, documented verbose diagnostic mode. |

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
| --- | --- | --- |
| AC-001 | Integration/regression | `tests/test_installer.py`, `tests/test_install_bootstrap.py`, `tests/test_install_cli_command.py` |
| AC-002 | Unit + CLI contract | New host-diagnostic tests with fake process/environment adapters and JSON golden assertions |
| AC-003 | Unit + integration | Workspace fixture tests for discovery, ambiguous candidates, and no-write behavior |
| AC-004 | Unit + integration | Session fixtures covering invalid JSON, missing tools, configs, ports, and MI-log states; assert no OpenOCD invocation |
| AC-005 | Regression + CLI contract | `tests/test_cli_flow.py` plus dedicated attach merge-plan/diff tests |
| AC-006 | Unit + JSON schema regression | Readiness model/rendering tests for status ordering, ownership, provenance, and approval flag |
| AC-007 | Manual + docs regression | README/docs review; command examples checked against parser help and JSON fixtures |
| AC-008 | Security unit + CLI contract | Tests prove untrusted inputs cannot change rendered argv/action IDs and every mutable action is approval-required |
| AC-009 | Security regression | Tests patch socket/subprocess/writes and assert default diagnostics cannot invoke target/OpenOCD transport paths |
| AC-010 | Security unit + integration | Symlink escape, unreadable-path, bounded-scan, and process-redaction fixtures |

## Test Plan

- Unit: model validation, ordering, platform/path parsers, tool discovery,
  configuration parsing, candidate ranking, remediation metadata, and diff
  rendering.
- Integration: CLI text/JSON output, fake host environments, fixture workspaces,
  existing VS Code configurations, and process/port evidence.
- Regression: current global `pipx` installer behavior, attach no-overwrite
  behavior, launch guard behavior, deterministic output, and no target mutation.
- Security: command-injection fixtures, denial-of-service-sized configuration
  inputs, symlink escape fixtures, redaction checks, forbidden socket/subprocess
  calls, and preview-only attach merge plans.
- Manual: one supported Linux distribution, one existing firmware workspace,
  one fresh workspace, missing `pipx`, missing OpenOCD, and a user-owned
  `launch.json` merge case.

## Risk Register

| Risk | Tier | Mitigation |
| --- | --- | --- |
| Unapproved host mutation initiated by an agent | Medium | CLI only reports remediation; all mutation candidates are marked approval-required; prompts reinforce the boundary. |
| Diagnostics accidentally interact with target hardware | High | Static/local checks only; process adapters are tested for forbidden OpenOCD/socket invocation; require `/security-review`. |
| Non-deterministic host or filesystem discovery | Medium | Explicit sort order, bounded directories, immutable reports, fixture-based regression tests. |
| Incorrect board/probe inference | Medium | No heuristic selection; require explicit user selection or checked-in profile. |
| Merge plan damages user-owned configuration | High | No automatic apply path in first slice; ownership checks, preview-only plans, parsing/round-trip tests; require `/security-review`. |
| Platform/distro scope balloons | Medium | Linux-first support matrix; unsupported environments yield evidence-backed blocks. |
| Workspace-controlled remediation runs arbitrary host commands | High | Typed allowlisted actions; never parse or execute command text from discovered input; explicit approval metadata. |
| Static diagnostic touches a target via reused OpenOCD code | High | Separate static module boundary and forbidden-call/import regression tests. |
| Report leaks paths or secrets from process arguments | Medium | Typed provenance, default redaction, output caps, and explicit verbose mode. |
| Discovery escapes workspace through symlinks | Medium | Resolved-root containment, no directory-symlink traversal, and fixture coverage. |

## Validation Commands

- `./scripts/verify.sh fast`
- Focused unit and CLI tests for the changed modules
- `/cli-qa`
- `/security-review`
- `./scripts/verify.sh full`

## Release / Compatibility Notes

This is an additive public CLI surface. The global `pipx` installer and existing
`init-workspace` behavior remain compatible. New JSON outputs must carry a
schema version; text output is human-facing and must not be parsed as a stable
API. No migration is needed because the first slice does not write new project
metadata or automatically alter user-owned VS Code files.
