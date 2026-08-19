# Automatic Workspace Initialization Code Review

Date: 2026-08-19

Gate: pre-landing `/review`

Reviewed range: `2a3d67c..f9aad79`, plus the fixes recorded by this audit

Task spec: [`AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md`](../plans/AUTOMATIC_WORKSPACE_INIT_TASK_SPEC.md)

Test plan: [`AUTOMATIC_WORKSPACE_INIT_TEST_PLAN.md`](../plans/AUTOMATIC_WORKSPACE_INIT_TEST_PLAN.md)

Risk register: [`AUTOMATIC_WORKSPACE_INIT_RISK_REGISTER.md`](../plans/AUTOMATIC_WORKSPACE_INIT_RISK_REGISTER.md)

## Result

The review gate passes with fixes. No critical or high-severity finding remains
open. CLI QA and the mandatory security review are still required before the
feature can be declared complete.

## Findings fixed during review

### High

- Automatic scaffold and register application could follow a symlinked
  `.vscode` or `.dbgoracle` output path and write outside the resolved workspace.
  Automatic application now rejects symlinked directories/files and non-regular
  output files before writing. Regression coverage proves external directories
  remain unchanged.

### Medium

- `--auto --attach --svd-file ...` could create or update
  `.vscode/settings.json`, including with `--force`, despite attach mode's
  fragment-only ownership contract. Attach mode now accepts an already-current
  setting but never persists a new or changed one.
- Automatic inventory could read `settings.json` or `launch.json` through a
  symlinked `.vscode` path. Those configurations are now ignored unless every
  path component is a trusted regular workspace file.
- Automatic document discovery applied a candidate limit only after an
  unbounded recursive walk. The shared discovery implementation now exposes a
  hard entry/candidate-bounded variant; automatic inventory uses it and marks
  the document class truncated so the planner selects nothing from it.
- An exception at the documentation application boundary or while persisting an
  SVD setting could abort the whole command and suppress independent capability
  results. Both boundaries now return deterministic `partial` application
  results and allow the remaining capabilities to proceed.
- A failed post-application re-inventory discarded all capability application
  evidence even though files or sidecars might already have been persisted. The
  command now retains the initial plan plus normalized application results,
  reports the re-inventory error, and returns `partial` when useful state exists.

## Remaining risks

### Medium, non-blocking for this gate

- Validation and filesystem application are separate operations. A concurrent
  same-user process could replace a validated input or output component between
  the checks and the later open/write. Closing this TOCTOU class completely
  requires descriptor-relative, no-follow filesystem operations and a broader
  cross-platform writer design. The new pre-write checks close the ordinary
  symlink workspace case; the mandatory security review must explicitly assess
  whether an adversarial concurrent-workspace threat model is required for this
  release.
- The three scaffold files are written individually by the existing workspace
  writer, not as one transaction. An I/O failure can therefore leave a subset
  of managed files. The automatic boundary reports `partial`, lists current
  workspace files, and an unchanged rerun is recoverable and idempotent. A
  transactional multi-file writer would be a separate architecture change.

Neither item permits silent overwrite of an already-present user-owned VS Code
file under the reviewed non-concurrent behavior.

## Invariant and scope assessment

- The Acquire → Normalize → Reduce → Persist → Render pipeline remains intact.
- Planning remains pure; discovered strings are retained as data and no build,
  network, socket, debugger, OpenOCD, or target action was added.
- Explicit non-automatic mode retains its parser requirements, ownership,
  attach, force, output, and exit-code paths.
- Capability ordering, ambiguity behavior, provenance, overall status mapping,
  post-application state, and unchanged rerun behavior remain deterministic.
- The bounded fixes are confined to automatic initialization and the shared
  document discovery primitive. Generated sidecar directories are pruned from
  document source discovery.
- No unrelated P0 planning file, `AGENTS.md`, or reference-workspace submodule
  content was changed by this review.

## Validation evidence

- `python3 -m unittest tests.test_auto_init_planner tests.test_auto_init_cli tests.test_docs_sidecar tests.test_cli_flow`
  - 141 tests passed.
- Focused `ruff-check`: passed.
- Focused `ruff-format`: passed.
- Focused `pyright`: passed.
- Repository fast/full validation remains the responsibility of the integration
  and ship gates.

## Downstream routing

- `qa_required: yes (cli-qa; public CLI contract changed)`
- `security_required: yes (high-risk local PDF/config parsing boundary)`
- `document_release_required: yes`
- `full_validation_required: yes`
