# Agent Setup Readiness Task Spec

Status: Complete (read-only readiness slice)

## Problem Statement

DebugOracle is correctly installed as a per-user global CLI through `pipx`, but
starting a usable embedded debug session still requires machine-specific debug
host dependencies and project-specific configuration. Users currently have to
discover those boundaries, missing dependencies, board inputs, VS Code merge
conflicts, and session failures themselves.

Provide an agent-assisted, deterministic readiness flow that makes the path
from an installed global CLI to a running Cortex-Debug/OpenOCD session explicit
and diagnosable without making DebugOracle a system-package installer or a
target-mutating debugger controller.

## Scope

- In scope:
  - Preserve the existing Linux `pipx` installer as the global CLI install path.
  - Add a read-only host diagnostic surface for debug-host prerequisites.
  - Add a read-only workspace planning surface that discovers and reports
    candidate inputs without choosing ambiguous board or probe facts.
  - Add a pre-launch session diagnostic surface that validates local
    configuration, workspace-contained paths, MI-log freshness, and local RTT
    listener evidence without contacting the target.
  - Document three explicit agent prompts: global CLI install, host readiness,
    and per-workspace connection.
- Out of scope:
  - Automatic installation of OS packages, VS Code, extensions, probe drivers,
    or udev rules.
  - Automatic target/probe detection that guesses a board or writes to target
    memory.
  - Flashing, resetting, halting, or otherwise contacting a target by default.
  - Attach-mode machine-readable merge plans or automatic application of
    user-owned VS Code configuration changes.
  - Board profiles and structured remediation actions.
  - Replacing Cortex-Debug, OpenOCD, or existing project build systems.
  - Windows and macOS support in the first slice.

## Invariants Touched

- Deterministic: identical discovered local state produces stable JSON, ordered
  diagnostics, and the same merge plan.
- Evidence-first: every readiness item includes its observed source and does not
  infer unobserved hardware state.
- Read-only: default diagnostics must not mutate host, workspace, artifacts, or
  target state.
- Reproducible: host facts, workspace inputs, and generated plans are explicit
  and serializable.
- Explicit provenance: candidate ELF/config/profile values name their file,
  command, or configuration source.

## Acceptance Criteria

- AC-001: `dbgoracle` remains a per-user global CLI installed through the
  supported `pipx` path; no workspace-local runtime installation is introduced.
- AC-002: A host diagnostic command returns deterministic text and JSON for
  Linux platform support, Python, `pipx`, OpenOCD, ARM GDB, VS Code,
  Cortex-Debug, PATH visibility, and known probe-permission evidence, with
  remediation that distinguishes read-only advice from an action needing user
  approval.
- AC-003: A workspace planning command inspects only the selected workspace and
  emits evidence-backed candidate ELF files, existing Cortex-Debug settings,
  OpenOCD config files, optional SVD files, and unresolved choices; it never
  selects among ambiguous candidates.
- AC-004: A session diagnostic command validates launch/task/settings JSON,
  executable and OpenOCD-config readability, required host tools, port
  conflicts, and MI-log destination freshness without starting OpenOCD or
  communicating with the target.
- AC-005: Default host/workspace/session diagnostics are statically read-only:
  they do not import or invoke OpenOCD TCP clients, start subprocesses beyond
  bounded local version/discovery probes, write workspace files, or communicate
  with target hardware.
- AC-006: Workspace discovery is bounded to the resolved workspace root, does
  not follow directory symlinks, excludes unreadable paths, and redacts
  excessive discovery output from default results.
- AC-007: README provides one short prompt for global CLI installation and one
  short prompt for agent-assisted project initialization.

## Risks

- Technical risk: varying Linux distributions, package locations, VS Code
  install forms, and probe permissions may make host detection incomplete.
- Operational risk: an agent may treat a remediation command as approved work,
  or users may mistake a local configuration check for a safe hardware probe.
- Security risk: untrusted workspace configuration or profile data could become
  host command input, or a diagnostic could accidentally reuse a live OpenOCD
  transport path.

## Rollback Plan

The new commands are additive. Remove their parser registrations and modules,
and retain the current installer and `init-workspace` attach behavior. Generated
merge plans are read-only outputs and do not require migration. Any future
owned metadata in generated files must be ignored safely by prior versions.
