# Agent Setup Readiness Test Plan

Status: Active

Task: [Agent Setup Readiness Task Spec](AGENT_SETUP_READINESS_TASK_SPEC.md)

| Area | Required coverage | Acceptance criteria |
| --- | --- | --- |
| Global install | Existing `pipx` installer success, upgrade, PATH, failed verify, and rerun paths remain unchanged. | AC-001 |
| Host doctor | Fake environment/process adapters cover each dependency, stable ordering, text/JSON schema, unsupported distro, redaction, timeout, and approval metadata. | AC-002, AC-006, AC-008, AC-009, AC-010 |
| Workspace plan | Fixture workspaces cover one candidate, ties, existing Cortex-Debug metadata, board profiles, unreadable paths, symlink escape, and zero writes. | AC-003, AC-006, AC-010 |
| Session doctor | Fixtures cover malformed JSON, missing tools/files, invalid config paths, listeners/port conflict evidence, stale MI destination, and zero socket/OpenOCD/target interaction. | AC-004, AC-006, AC-009 |
| Attach merge plan | Existing user-owned VS Code JSON returns deterministic merge-plan JSON and display diff; no apply/write path exists. | AC-005, AC-009 |
| Agent documentation | Prompt text requires repository instructions, supported commands, approval for host mutation, and phase separation. | AC-007, AC-008 |

## Required Regression Guards

- Patch sockets, OpenOCD client imports, workspace writes, and unapproved
  subprocess calls to fail in default diagnostic tests.
- Assert all discovered paths are sorted, within the resolved workspace root,
  and free of directory-symlink traversal.
- Assert untrusted profile/workspace/process input cannot alter a remediation
  action ID or rendered argv.
- Run every deterministic fixture twice and compare normalized JSON exactly.

## Validation Sequence

1. Focused unit and command tests during implementation.
2. `./scripts/verify.sh fast` before review.
3. `/review`, then `/cli-qa` in full mode on the new command surface.
4. Re-run `/security-review` against the implementation.
5. `./scripts/verify.sh full` before handoff.
