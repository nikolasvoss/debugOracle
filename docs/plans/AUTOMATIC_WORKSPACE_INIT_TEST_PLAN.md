# Automatic Workspace Initialization Test Plan

Status: Approved for TDD implementation

Task: [Automatic Workspace Initialization Task Spec](AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md)

## Acceptance Criteria to Validation Mapping

| Acceptance criterion | Automated validation | Manual/gate validation |
| --- | --- | --- |
| AC-AWI-001 | Parser and CLI regression tests compare explicit mode with its current required-input, output, write, and exit behavior; auto mode accepts omitted inputs. | `/cli-qa` command-contract comparison. |
| AC-AWI-002 | Discovery fixtures cover bounded scans, truncation by class, symlink files/directories, outside-root paths, unreadable entries, deduplication, and stable ordering; spy/assert that the shared workspace/docs discovery paths are used. | `/security-review` containment review. |
| AC-AWI-003 | Table-driven planner tests cover explicit/zero/one/multiple candidates for every input and compare plans across reversed creation orders. | None. |
| AC-AWI-004 | JSONC fixtures cover zero/one/multiple Cortex-Debug configurations, empty/non-string/outside-root `configFiles`, unrelated launches, and raw `.cfg` candidates. | CLI QA verifies actionable ambiguity output. |
| AC-AWI-005 | Fixtures cover explicit SVD, existing setting, one `.dbgoracle/*.svd`, multiple SVDs, missing SVD, and precedence. | None. |
| AC-AWI-006 | CLI integration tests prove `--yes` invokes existing docs ingest, missing `--yes` performs zero parser calls/writes, multiple PDFs are sorted, and per-document results survive. | CLI QA tests the copy-PDF-and-init flow. |
| AC-AWI-007 | Toolchain-free temporary workspace with one PDF and no ELF/OpenOCD/SVD returns exit `2`, docs `complete`, hardware capabilities actionable, and searchable sidecars. | Run the bundled demo in a clean clone without embedded tools. |
| AC-AWI-008 | Fault-injection tests make docs parsing, scaffold writing, or one document fail independently and assert unaffected capabilities still run and are reported. | None. |
| AC-AWI-009 | Existing settings/launch/tasks fixtures are hashed before/after; attach fragments and managed-file `--force` regression tests remain green. | Review a real Cortex-Debug fixture diff. |
| AC-AWI-010 | Tests patch network, socket, subprocess/build, OpenOCD/live-client entrypoints, and downloads to fail if invoked; auto init still completes its local plan. | `/security-review` verifies imports and call graph. |
| AC-AWI-011 | Golden text/JSON tests assert schema, stable capability/action/path ordering, provenance, status/exit mappings, stdout/stderr separation, and equality after creation-order reversal. | `/cli-qa` checks agent usability. |
| AC-AWI-012 | Run automatic init twice; compare input hashes and artifact hashes/mtimes, and compare normalized JSON results. | None. |
| AC-AWI-013 | Documentation contract tests assert exact `docs/vendor/`, `.dbgoracle/<device>.svd`, command/prompt, legal source boundary, and no claimed download. | `/document-release` sync review. |

## Required Test Layers

### Pure planner unit tests

- One table per input kind for precedence, absence, unique selection, ambiguity,
  invalid path, and truncation.
- Capability and overall status reduction for all meaningful combinations.
- Stable provenance and required-action identifiers.
- Creation-order-independent normalized plans.

### Discovery and parsing-boundary tests

- Reuse `collect_workspace_plan` and the shared docs discovery primitive.
- Root/direct documented scan locations only; no directory-symlink traversal.
- Bounded candidate classes with explicit truncation evidence.
- JSONC size/type validation and workspace containment.
- Existing sidecar directories and generated files never become source inputs.

### CLI integration tests

- `--auto`, `--auto --yes`, `--format text`, and `--format json`.
- Docs-only, full unique-input, no-input, ambiguous, mixed-success, blocked
  user-owned VS Code, and managed rerun workspaces.
- Explicit arguments override discoveries without suppressing unrelated docs.
- Exit codes `0`/`2`/`1` and stdout/stderr contracts.
- Actual lexical docs search succeeds after the docs-only flow.

### Regression tests

- Every existing explicit `init-workspace` test remains green.
- Existing `workspace plan`, `docs ingest/search/status`, fetch SVD precedence,
  attach fragments, RTT settings, and ownership marker tests remain green.
- No artifact or public schema unrelated to automatic initialization changes.

## TDD Sequence

1. Red: parser mode split and pure planner precedence/status tests.
2. Green: minimal mode validation and immutable plan/result models.
3. Red: discovery containment, ambiguity, truncation, and launch/SVD precedence.
4. Green: extend/reuse workspace plan and docs discovery without a second walk.
5. Red: docs-only and mixed-capability CLI integration tests.
6. Green: independent application and result aggregation using existing writers.
7. Red/green: idempotence, failure isolation, stable renderers, and live-I/O
   tripwires.
8. Refactor only after all explicit-mode regressions pass.

## Validation Sequence

1. Focused planner/discovery tests.
2. Focused `init-workspace`, readiness, docs, and reference-workspace tests.
3. `./scripts/verify.sh fast`.
4. `/review` with unresolved structural issues fixed before QA.
5. `/cli-qa` in full mode because the public CLI contract changes.
6. `/security-review` because automatic PDF parsing makes the slice high risk.
7. `/document-release` for specs, README, changelog, and plan status.
8. `./scripts/verify.sh full` before completion.

Completion may not be claimed if any focused test, required gate, or full
validation fails.
