# Public Alpha Demo and Workspace Initialization Handoff

Status: automatic initialization implemented and documentation synchronized on
2026-08-19; pre-landing review and release validation remain pending.

This document records the implemented hardware-free demo and automatic
workspace initialization, plus the exact remaining release gates. It
distinguishes completed implementation from validation that has not yet run.

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
- `6f2b00b feat: apply automatic workspace initialization`
- `94e375e fix: contain automatic document discovery`
- `ca51a17 feat: plan automatic workspace initialization`
- `2a3d67c docs: pin portable demo SVD flow`
- `8ffc58b docs: plan automatic workspace initialization`
- `9b1b4c5 docs: record demo initialization handoff`
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

Final release review, demo CLI QA, security review, and
`./scripts/verify.sh full` have not yet been run for the complete slice.

## Completed automatic-initialization slice

The approved behavior in `AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md` is implemented
through `6f2b00b`. The public golden path is:

```bash
dbgoracle init-workspace --workspace-root . --auto --yes --format json
```

Implemented behavior includes:

- bounded, local-only inventory through the existing workspace-plan path;
- deterministic selection or ambiguity reporting for ELF, SVD, and existing
  Cortex-Debug `configFiles` inputs;
- independent documentation, debug-scaffold, and register-catalog capability
  application;
- explicit `--yes` authorization before discovered PDFs are parsed;
- docs-only initialization without a toolchain, board, probe, executable, or
  OpenOCD configuration;
- versioned JSON and deterministic text results with provenance, status, and
  ordered next actions;
- no build, network/download, probe, debugger transport, or target access;
- idempotent reruns and preservation of user-owned VS Code files.

The earlier standalone SVD-path concern is resolved by `2a3d67c`: the
hardware-free demo relies on the register catalog already embedded in its
committed snapshot and does not require an external SVD. Live users are told to
place their exact-device SVD at `.dbgoracle/<device>.svd`.

## Remaining release slice

Do not modify the existing untracked P0 planning files until their ownership
and intended contents have been reconciled. The implementation is complete;
the remaining work is verification and release readiness:

1. Run the pre-landing `/review` gate over the complete implementation diff.
2. Run `/cli-qa` against explicit legacy init, auto planning without consent,
   docs-only auto init, full unambiguous auto init, ambiguity, and rerun flows.
3. Run the mandatory `/security-review` for the untrusted local PDF/JSONC/path
   boundary and confirm zero network, subprocess, socket, or target access.
4. Run `./scripts/verify.sh full`; do not claim release completion while any
   hook fails.
5. Reconcile the user-owned P0 planning files separately and update their state
   only with explicit ownership.

## Resume commands

```bash
git switch codex/demo-docs-init-flow
git -C examples/debugoracle-reference-workspaces switch codex/demo-docs-init-flow
git status --short --branch
git -C examples/debugoracle-reference-workspaces status --short --branch
python3 -m unittest tests.test_reference_workspace_samples
python3 -m unittest tests.test_auto_init_planner tests.test_auto_init_cli
python3 -m unittest tests.test_auto_init_docs
```

At resume time, first confirm that the two branches and commit IDs above are
still present and that the pre-existing user files remain untouched. Then run
the remaining review, CLI QA, security, and full-validation gates in that order.
