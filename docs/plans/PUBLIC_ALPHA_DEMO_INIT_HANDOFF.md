# Public Alpha Demo and Workspace Initialization Handoff

Status: paused at a clean implementation boundary on 2026-08-19.

This document records the implemented hardware-free demo, the remaining
automatic workspace-initialization work, and the exact point from which to
continue. It distinguishes shipped behavior from proposed behavior; the latter
must not be presented as implemented until its task spec and tests are complete.

## Product intent

The public demo should work after cloning the repository and opening the demo
folder in a new VS Code window. No embedded toolchain, probe, board, or live
target is required. The user's existing coding agent may use the internet, but
the deterministic demo evidence and the limited documentation needed for the
showcase are bundled in the repository.

The strongest showcase is evidence synthesis across independent sources:

1. observe the serial failure in recorded RTT evidence;
2. inspect the firmware source that configures USART1;
3. read `RCC_CCIPR` and `USART1_BRR` from the recorded register evidence;
4. retrieve the relevant clock-selection and baud-rate facts from the bundled
   demo reference;
5. explain the diagnosis while separating observations, documentation,
   conclusions, and remaining gaps.

The bundled reference is project-authored and independently worded. It covers
only the RCC/USART facts needed by the demo. The ST reference manual itself is
not redistributed; the demo points users to ST's official documentation page.

For a real project, the intended user experience is equally direct: copy PDFs
to `docs/vendor/`, place exactly one default SVD at
`.dbgoracle/<device>.svd`, then ask the agent to initialize the workspace. All
capabilities with unambiguous inputs should be initialized, while missing or
ambiguous inputs should produce precise next actions rather than guesses.

## Repository state

Main repository:

- branch: `codex/demo-docs-init-flow`
- `f3a64b6 test: lock reproducible demo evidence`
- `9b34ca2 docs: add hardware-free agent demo flow`
- base: `7d277af docs: sync dependency audit status`

Reference-workspaces submodule:

- path: `examples/debugoracle-reference-workspaces`
- branch: `codex/demo-docs-init-flow`
- `69ce977 demo: add reproducible peripheral evidence fixture`
- `26bdf81 docs: add hardware-free docs demo reference`
- base: `75e2c82 chore: sanitize public reference workspaces`

The following main-worktree files predated this slice and are intentionally not
owned by it. Do not overwrite, stage, or delete them without reconciling their
contents with the user:

- modified `AGENTS.md`
- untracked `docs/plans/PUBLIC_ALPHA_P0_PLAN.md`
- untracked `docs/plans/PUBLIC_ALPHA_P0_RISK_REGISTER.md`
- untracked `docs/plans/PUBLIC_ALPHA_P0_TASK_SPEC.md`
- untracked `docs/plans/PUBLIC_ALPHA_P0_TEST_PLAN.md`

## Completed demo slice

The reference workspace now contains:

- `stm32/peripheral-miscfg/doc/debugoracle_demo_stm32l4_reference.md`
- `stm32/peripheral-miscfg/doc/debugoracle_demo_stm32l4_reference.pdf`
- `stm32/peripheral-miscfg/samples/snapshot.json`
- `stm32/peripheral-miscfg/samples/report.txt`
- explicit demo instructions in the workspace `README.md` and `AGENTS.md`
- vendor-document placement guidance in `stm32/vendor-downloads.md`

The two-page PDF documents the demo-relevant `RCC_CCIPR`, USART1 clock
selection, `USART_CR1`, and `USART_BRR` facts. Its SHA-256 is:

```text
4adde7e0393a896939554e57c23dd1ef64294ec1d94a764328ca2f049e255095
```

The sample snapshot is explicitly marked as a deterministic project-authored
fixture, not a live measurement. It records:

- GDB/MI evidence;
- RTT evidence containing `OBS: serial_path=fault code=-2`;
- SVD-backed RCC and USART1 register evidence;
- `RCC_CCIPR = 0x00000002`, selecting HSI16 for USART1;
- `USART1_BRR = 0x000002B6`, configured for 80 MHz and 115200 baud;
- firmware source that selects HSI16, yielding the demonstrable clock/baud
  mismatch.

The main README provides a copyable agent prompt for both the bundled demo and
a fresh project. The demo agent instructions ingest the bundled PDF, render the
recorded snapshot, search the indexed documentation, inspect the firmware, and
present a provenance-aware diagnosis.

## Validation already completed

- `python3 -m unittest tests.test_reference_workspace_samples`: 15 tests passed.
- Temporary-workspace end-to-end PDF ingestion succeeded with the `pypdf`
  parser: 2 pages and 2 chunks.
- BM25 search over that temporary index returned the relevant demo pages.
- The committed text report exactly matched a fresh CLI rendering.
- The PDF was rendered and visually inspected with Poppler.
- A deterministic PDF rerender produced the same SHA-256.
- Commit hooks passed for both main-repository commits: Ruff, Ruff format,
  Pyright, pytest-fast, coverage, and Bandit.

Final release review, demo CLI QA, and `./scripts/verify.sh full` have not yet
been run for the complete future slice.

## Known limitation at the pause point

General automatic initialization of an arbitrary user project is not yet
implemented. The current experience is agent-guided: repository instructions
tell the agent which existing DebugOracle commands to run and prohibit guessing
missing board settings.

Also verify the demo's SVD path before claiming that the reference-workspaces
repository works as a standalone clone. Its VS Code settings currently refer to
`../../../STM32L432.svd`, which works in the main repository's submodule layout
but may not resolve when the reference repository is cloned alone. Decide
whether to bundle an appropriately licensed SVD in the reference repository or
make path discovery independent of the parent checkout.

## Next implementation slice

This is a public behavior change and must follow
`docs/workflows/AGENT_WORKFLOW_RULES.md`. Before coding, write a focused task
spec and test plan for automatic initialization. Do not modify the existing
untracked P0 planning files until their ownership and intended contents have
been reconciled.

First inspect the smallest relevant surface:

- `docs/specs/init_workspace.md`
- `debugoracle/cli/commands/init_workspace.py`
- the existing readiness or workspace-plan command and its tests
- the nearest `init-workspace` CLI tests

Then choose the smallest extension of the existing architecture. In
particular, determine whether the existing workspace-plan/readiness machinery
can provide discovery and planning without introducing another overlapping
command.

The task spec should lock these requirements:

1. Discover documentation only in documented project locations such as
   `doc/`, `docs/`, and especially `docs/vendor/`.
2. Use a single `.dbgoracle/*.svd` automatically; report multiple candidates as
   ambiguous.
3. Discover ELF/build outputs deterministically and never select arbitrarily.
4. Reuse an unambiguous existing Cortex-Debug/OpenOCD configuration when
   available.
5. Initialize and ingest documentation independently when hardware-debug inputs
   are missing.
6. Report each capability as complete, partial, or unavailable, with exact next
   actions and paths.
7. Perform no probe connection, target mutation, or live acquisition during
   initialization.
8. Never download, move, or infer proprietary vendor inputs silently.
9. Preserve deterministic output and explicit provenance.

Recommended TDD order:

1. discovery/planning tests for one valid candidate, no candidate, and multiple
   candidates;
2. docs-only initialization with no toolchain or OpenOCD configuration;
3. mixed-capability initialization where docs succeed and hardware setup stays
   partial;
4. idempotent rerun and deterministic JSON/text output;
5. CLI integration tests for exit codes, stdout/stderr, and actionable paths;
6. only then the smallest implementation changes.

## Remaining showcase work

After automatic initialization is implemented:

- add a concise README transcript showing the agent connecting RTT, source,
  RCC clock selection, BRR, and documentation evidence;
- make clear that the value is reliable access to heterogeneous evidence, not
  merely generic agent reasoning;
- resolve the standalone SVD-path issue;
- run the pre-landing review, CLI QA for the user-facing flow, documentation
  sync, and full repository validation;
- update the changelog only with behavior that actually shipped.

## Resume commands

```bash
git switch codex/demo-docs-init-flow
git -C examples/debugoracle-reference-workspaces switch codex/demo-docs-init-flow
git status --short --branch
git -C examples/debugoracle-reference-workspaces status --short --branch
python3 -m unittest tests.test_reference_workspace_samples
```

At resume time, first confirm that the two branches and commit IDs above are
still present and that the pre-existing user files remain untouched. Then write
the automatic-initialization task spec and test plan before starting its TDD
implementation.
