# Automatic Workspace Initialization CLI QA

| Field | Value |
|---|---|
| Date | 2026-08-21 |
| Baseline | CLI matrix `08a5f39`; final revalidation `b4fd219` |
| Command | `./dbgoracle init-workspace` |
| Mode | `full` |
| Scope | Automatic workspace initialization public CLI contract |
| Measured CLI time | 18.6 seconds (fixture setup and analysis excluded) |
| Outcome | **PASS** |
| Workspace root | `/tmp/dbgoracle-auto-cliqa.0FEl60` (bounded, ephemeral cases) |

Task spec:
[`AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md`](../plans/AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md)

Prior gates:
[`automatic-workspace-init-code-review.md`](automatic-workspace-init-code-review.md),
[`automatic-workspace-init-security-review.md`](automatic-workspace-init-security-review.md)

## Result

The CLI behavior matrix passes. All 14 command runs returned their documented
exit class, emitted parseable or expected help output on stdout, emitted zero
bytes on stderr, and produced only the authorized workspace artifacts. No CLI
blocker was found.

The original command matrix ran with locally installed `pypdf==6.9.2`. Final
ship validation on 2026-08-21 proved `pypdf==6.16.1` in both the checkout Python
and pipx DebugOracle environments, then repeated the focused real-PDF, search,
malformed-PDF, automatic-init, idempotence, and reference-workspace coverage.
All 105 focused tests passed, so the earlier ship-environment constraint is
resolved and the gate is promoted to **PASS**.

## Health Score: 98/100

| Category | Score |
|---|---:|
| Command availability | 100 |
| Contract stability | 100 |
| Output determinism | 100 |
| Error handling | 100 |
| Reproducibility | 100 |
| Security hygiene | 90 |

The rounded aggregate is 98. Security hygiene retains a small reduction for the
three already tracked non-blocking residual risks; this run found no new unsafe
CLI behavior.

## Blocked Findings (Must Fix)

None in the automatic-initialization CLI behavior.

## Resolved Ship-Environment Constraint

1. **CLIQA-AWI-001: declared PDF parser target not exercised — resolved
   2026-08-21.** Checkout Python reports `pypdf 6.16.1` from
   `/home/niko/.local/lib/python3.12/site-packages`, and the pipx DebugOracle
   environment reports 6.16.1 from
   `/home/niko/.local/pipx/venvs/debugoracle/lib/python3.12/site-packages`.
   The 105-test focused revalidation covers authorized real-PDF ingestion,
   search, malformed-PDF isolation, and unchanged automatic-init reruns.

## Review-Only Findings

1. **CLIQA-AWI-002: descriptor-atomic path use remains out of scope** — The
   security audit records a same-user concurrent replacement window after path
   validation. Ordinary outside-root and symlink cases passed here.
2. **CLIQA-AWI-003: PDF parsing remains in-process** — The CLI has no OS-level
   CPU, memory, or wall-clock envelope around pypdf. This bounded run completed
   without a hang; future parser defects remain a tracked risk.
3. **CLIQA-AWI-004: scaffold publication is recoverable, not transactional** —
   The three managed VS Code files are separate writes. No induced I/O-failure
   test was added to this black-box matrix; the code/security reviews retain
   the structured-partial and rerun recovery evidence.

## Command Matrix

`$QA_ROOT` below is the bounded workspace root shown in the report header.
Every row used `./dbgoracle`, no hardware, network, install, or background
process, and separate stdout/stderr captures.

| Case and command | Exit | Stdout / stderr | Assertions and artifacts | Result |
|---|---:|---|---|---|
| Help: `init-workspace --help` | 0 | 2,527 B help / 0 B | Lists `--auto`, `--yes`, explicit input flags, and `{text,json}` | Pass |
| Empty: `--workspace-root $QA_ROOT/empty --auto --format json` | 1 | 1,466 B JSON / 0 B | Schema `1`; scope `automatic_workspace_init`; ordered capabilities all `unavailable`; zero files written | Pass |
| No consent: `--workspace-root $QA_ROOT/docs_no_yes --auto --format json` | 2 | 1,822 B JSON / 0 B | `partial`; PDF reported with `workspace_discovery`; first action `authorize_document_ingest`; application not attempted; no sidecar, `.vscode`, or `.dbgoracle`; source unchanged | Pass |
| Docs only: `--workspace-root $QA_ROOT/docs_yes --auto --yes --format json` | 2 | 2,027 B JSON / 0 B | Overall `partial`; documentation `complete`; pypdf, 2 pages, 2 chunks, clean; hardware capabilities unavailable | Pass; revalidated with 6.16.1 |
| Search: `docs search USART --workspace-root $QA_ROOT/docs_yes --format json` | 0 | 4,817 B JSON / 0 B | BM25; two clean hits; results contain `USART1SEL`, `USART_CR1`, and `USART_BRR` evidence | Pass; revalidated with 6.16.1 |
| Full: `--workspace-root $QA_ROOT/full --auto --yes --executable build/app.elf --svd-file .dbgoracle/device.svd --openocd-config config/interface.cfg --openocd-config config/target.cfg --format json` | 0 | 3,583 B JSON / 0 B | Overall and all three capabilities `complete`; capability order fixed; docs provenance `workspace_discovery`; ELF/SVD/OpenOCD provenance `explicit`; five generated artifacts | Pass; revalidated with 6.16.1 |
| Ambiguity: `--workspace-root $QA_ROOT/ambiguous --auto --format json` | 2 | 2,411 B JSON / 0 B | Two ELF and two SVD candidates yield `choose_executable` and `choose_svd`; no candidate guessed; no `.vscode` writes | Pass |
| User-owned VS Code: `--workspace-root $QA_ROOT/owned --auto --executable build/app.elf --openocd-config config/target.cfg --format json` | 2 | 5,938 B JSON / 0 B | Scaffold `partial`; all three existing files listed as blocked; before/after SHA-256 sets identical | Pass |
| Full identical rerun: same full command | 0 | 3,583 B JSON / 0 B | First/second stdout byte-identical; all five artifact SHA-256 values identical | Pass; revalidated with 6.16.1 |
| Malformed PDF: full explicit inputs plus `docs/broken.pdf` and `--yes` | 2 | 3,912 B JSON / 0 B | Documentation `partial`, `ingest_state=failed`, controlled pypdf warning; scaffold/register still `complete`; source unchanged | Pass; revalidated with 6.16.1 |
| Missing explicit path: valid ELF plus `--openocd-config missing.cfg` | 1 | 239 B JSON / 0 B | `failed`; exact `automatic input does not exist` error; no managed output | Pass |
| Outside explicit path: valid ELF plus outside-root config | 1 | 295 B JSON / 0 B | `failed`; exact `outside the workspace` error; no managed output | Pass |
| Symlink explicit path: valid ELF plus symlinked config | 1 | 252 B JSON / 0 B | `failed`; exact `must not use symlinks` error; no managed output | Pass |
| Legacy explicit init: `--workspace-root $QA_ROOT/legacy --executable build/app.elf --openocd-config config/target.cfg --format json` | 0 | 1,159 B JSON / 0 B | Legacy payload remains `complete`; exactly settings, launch, and tasks files created | Pass |

## Determinism and Artifact Evidence

The full first and second JSON captures were byte-identical, not merely equal
after parsing. SHA-256 inventories were also byte-identical across the rerun:

| Generated artifact | Size | SHA-256 |
|---|---:|---|
| `.vscode/launch.json` | 1,010 B | `127b0c9aaa82456140f5f040c273abee3d4e4181a11ffcd6f1c45108b7393153` |
| `.vscode/settings.json` | 933 B | `40c0155468869401b577b515491315b789ce9095ad5afebb6c7e0a1788ec28ec` |
| `.vscode/tasks.json` | 524 B | `21feabc8b8590ab2a6cb002889b3e4634bc41a30df4f86af64781787aa5b2ed5` |
| `reference.pdf.dbgoracle-docs/envelope.json` | 556 B | `5f19af35498b28ffd29fad720be0eb50416eab64a0e627bedef5a9ed180d3948` |
| `reference.pdf.dbgoracle-docs/index.json` | 21,020 B | `0cf2127157fbee1258e2ab44c4c01558861812256e8afa139b8710c61c8a90f3` |

The 7,581-byte project-owned PDF remained byte-identical to
`examples/debugoracle-reference-workspaces/stm32/peripheral-miscfg/doc/debugoracle_demo_stm32l4_reference.pdf`
in the no-consent, docs-only, and full cases. Its SHA-256 is
`4adde7e0393a896939554e57c23dd1ef64294ec1d94a764328ca2f049e255095`.

The user-owned preservation case retained these hashes:

| File | SHA-256 before and after |
|---|---|
| `.vscode/launch.json` | `9a9d24a3a023ff0b4cf7451fb0c67f41d45f0ca97d015e9562d3f12f08c235ab` |
| `.vscode/settings.json` | `c661c9fa33ba6d17b1efde33e3a4a4a26dd0766d52ab17c6d748aa1cc1e45854` |
| `.vscode/tasks.json` | `5c4e4a06af62fcb0072c71094f51248bbb85b5585b2dec090b3e43830cd36cba` |

The malformed-PDF case persisted deterministic failure evidence rather than
raising or suppressing independent capabilities: a 662-byte `envelope.json`
and an empty-index JSON array (`index.json`, 2 bytes).

## Severity Summary

| Severity | New CLI defects | Review-only / environment |
|---|---:|---:|
| Critical | 0 | 0 |
| High | 0 | 0 |
| Medium | 0 | 3 |
| Low | 0 | 0 |
| **Total** | **0** | **3** |

## Reproduction Notes

- Fixtures were confined to one `mktemp -d` root under `/tmp`.
- The executable fixture was a workspace-local copy of `/bin/true`; the SVD
  fixture was `tests/fixtures/sample.svd`; config fixtures were empty regular
  files because initialization stores paths and does not execute OpenOCD.
- The PDF fixture was the bundled, project-owned two-page demo reference named
  above. No restricted vendor material was used.
- Raw stdout/stderr captures and hash inventories were kept under the ephemeral
  QA root during analysis. The command matrix records their sizes and decisive
  assertions without embedding large extracted document text.
- This gate did not alter CLI code, `AGENTS.md`, P0 files, or the reference
  workspace submodule.
- Final 6.16.1 revalidation ran the checkout test modules for the automatic
  planner/CLI/docs contract, docs sidecar and CLI rendering, and reference
  workspace: 105 tests passed. `./scripts/verify.sh full` subsequently passed
  Ruff, Ruff format, Pyright, pytest-fast, coverage, and Bandit.

## Next Action

No CLI-QA blocker remains. Preserve the exact dependency pin and retain
CLIQA-AWI-002 through CLIQA-AWI-004 as non-blocking follow-up risks.
