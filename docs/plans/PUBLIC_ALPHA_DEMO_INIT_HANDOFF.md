# Public Alpha Demo and Workspace Initialization Handoff

Status: completed; the private `v0.2.0` release was withdrawn before public availability.

This document records the implemented hardware-free demo and automatic
workspace initialization, the completed release gates, and the final
publication state.

## Withdrawn release state

- The original `v0.2.0` tag and GitHub release were withdrawn before public
  availability as part of private-data cleanup.
- Reference-workspaces `main` points to
  `36934bd168aef6541a3c74bf6ef579b15447505c`.
- No replacement release has been created; later work will be released under a
  newly selected version.

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

## Pre-publication repository state

Main repository:

- branch: `codex/demo-docs-init-flow`
- ship-validation baseline: `b4fd219 docs: record automatic workspace init CLI QA`
- `08a5f39 security: harden automatic document initialization`
- `799bfa7 fix: harden automatic workspace initialization`
- `f9aad79 docs: pin automatic demo agent flow`
- `0ffbddd docs: publish automatic init showcase`
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

The user-owned `AGENTS.md` change and four P0 planning files were deliberately
left untouched during implementation. They were reconciled separately after
publication so their ownership and historical status remained clear.

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

The final review, CLI-QA, security, document-release, and full-validation gates
are recorded below.

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

## Final release validation

Local ship status: **ready**.

- Pre-landing code review: passed with fixes; no critical or high-severity
  finding remains open.
- Mandatory high-risk security review: passed with fixes. The descriptor-atomic
  filesystem window, in-process parser resource envelope, and recoverable
  multi-file scaffold publication remain documented non-blocking risks.
- CLI QA: passed. The 14-case behavior matrix had no CLI blocker, and its former
  parser-version constraint is resolved.
- Checkout version evidence: `pypdf 6.16.1` from
  `/home/niko/.local/lib/python3.12/site-packages/pypdf/__init__.py`.
- pipx DebugOracle version evidence: `pypdf 6.16.1` from
  `/home/niko/.local/pipx/venvs/debugoracle/lib/python3.12/site-packages`.
- Focused 6.16.1 revalidation:
  `python3 -m unittest tests.test_auto_init_planner tests.test_auto_init_cli tests.test_auto_init_docs tests.test_docs_sidecar tests.test_docs_cli_and_status_capture tests.test_reference_workspace_samples`
  passed all 105 tests.
- `./scripts/verify.sh full`: passed Ruff, Ruff format, Pyright, pytest-fast,
  coverage, and Bandit.
- Document-release gate: README commands and placement guidance, affected
  specifications, and `changelog.md` describe the implemented behavior. No
  additional README, spec, changelog, or TODO edit was required.
- Worktree ownership check: the modified `AGENTS.md` and four untracked P0 plan
  files remain untouched and unstaged; the reference-workspace submodule was
  not changed by final validation.

The local gate did not fetch, pull, push, compare a remote base, or resolve a
remote integration branch. Those actions were completed afterward: origin/main
was merged and validated, both repositories were pushed, and `v0.2.0` was
published. The user-owned P0 planning files were reconciled only after explicit
authorization.

## Closure

No publication action remains for the withdrawn `v0.2.0` implementation. Future
changes must select a new release version and preserve the documented provenance
limitations and residual security risks.
