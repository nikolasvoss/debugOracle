# Public Release Hardening Implementation Plan

**Status:** Implemented; external release gates remain open

## Task Link

`docs/plans/PUBLIC_RELEASE_HARDENING_TASK_SPEC.md`

Related artifacts:

- `docs/plans/PUBLIC_RELEASE_HARDENING_TEST_PLAN.md`
- `docs/plans/PUBLIC_RELEASE_HARDENING_RISK_REGISTER.md`

## Scope Review

- Mode: `HOLD_SCOPE`.
- Rationale: the public value is reliable installation and trustworthy evidence,
  not additional features. Every work item closes a reproduced release defect,
  a documented public contract, or an existing provenance gate.
- Accepted supporting work: centralized safe writes, artifact build smoke,
  Python compatibility matrix, and deterministic release metadata checks.
- Deferred: new backends, new reports, PyPI, optional profile enablement,
  non-Linux support, and making the verified GitHub Release wheel the default
  end-user onboarding path. Release 0.3.0 retains the explicit checkout-local
  installer as its documented user path; a later task may separate that
  contributor workflow from a standalone verified-wheel installer.
- Maintainer exception, 2026-08-24: pull-request and `main` CI temporarily skip
  the private reference-workspace checkout and its content-dependent tests.
  The exception expires before a release tag: tagged validation remains strict,
  and `ROADMAP.md` tracks publication of the reference repository plus removal
  of the exception.
- Rejected: weakening runtime and security contracts or declaring unresolved
  provenance verified.

## Engineering Review

- Risk tier: `high` because the task crosses filesystem, process signaling,
  installer execution, data integrity, and release supply-chain boundaries.
- Status: `issues_open` until third-party provenance and real-HIL evidence are
  supplied. Those issues block release, not implementation of the code work.
- Required downstream stages: TDD, code review, full CLI QA, security review,
  documentation release review, ship gate, and manual HIL validation.
- Major unresolved decision: none for code architecture. The provenance gate has
  two explicit outcomes: add traceable evidence or remove the affected assets.

## Delivery Strategy

Use five sequential, reviewable PRs. Each PR branches from the updated target
branch after its predecessor lands. Do not combine the changes into one diff.
All behavior-changing PRs link the task spec, this plan, and the relevant ACs.

1. `fix/release-build-and-clean-clone`
2. `fix/evidence-write-and-parser-safety`
3. `fix/installer-trust-and-versioning`
4. `fix/cli-contract-and-doc-sync`
5. `release/v0.3.0-candidate`

The branch names are suggestions for the implementation repository. In Codex,
prefix them with `codex/`.

## Architecture Decisions

### Safe host-filesystem writes

Add a small internal module, provisionally `debugoracle/safe_io.py`, with two
explicit policies rather than a generic wrapper:

1. **Workspace-derived output**
   - requires a canonical workspace root;
   - walks directories using Linux descriptor-relative operations;
   - opens directories with `O_DIRECTORY | O_NOFOLLOW`;
   - rejects `..`, symlink components, non-directory components, and resolved
     destinations outside the workspace;
   - never silently changes an unsafe path into a different path.
2. **Explicit user output**
   - may be outside the workspace only when supplied explicitly by the user;
   - still rejects a symlink final target and unsafe replacement;
   - reports the exact rejected path.

Expose narrow primitives:

- `atomic_write_text(...)` / `atomic_write_bytes(...)` for canonical state;
- `open_stream_output(...)` for RTT/run log append or truncate with
  `O_NOFOLLOW`;
- a domain exception translated by CLI commands into controlled stderr and
  stable exit codes.

Atomic writes create a same-directory temporary file with an exclusive name,
write all bytes, flush, `fsync` the file, replace descriptor-relatively, and
`fsync` the directory. Cleanup is best-effort and cannot remove a path outside
the already-open directory. A temporary-name nonce is never serialized or
included in user-visible success output; deterministic final bytes remain the
contract. Do not use validate-then-`Path.write_text`, because that retains the
discovered TOCTOU window.

Classify every existing write site before migration:

- canonical state: snapshots, persisted pipeline inputs, RTT state, run
  metadata;
- streaming state: RTT capture log and run log;
- explicit rendered output: report/status/fetch outputs;
- managed setup: workspace init and managed ignore/config files;
- independently safe staging: docs sidecar staging and atomic directory swap;
- installer-owned user profile writes.

Only migrate a site after its ownership, containment, overwrite, and recovery
contract is recorded in the test. Preserve docs-sidecar staging behavior unless
an adversarial test proves it unsafe.

### Process identity

Version run metadata and record:

- PID;
- `/proc/<pid>/stat` start-time ticks;
- canonical executable identity;
- exact argv shape expected for `dbgoracle run`;
- canonical workspace root;
- runtime metadata schema version.

Before SIGTERM and again before SIGKILL, read `/proc` and require every field to
match. Treat missing `/proc`, permission errors, malformed metadata, PID reuse,
or changed argv as an identity mismatch. Do not signal on a mismatch. A legacy
runtime file without strong identity fields is reported as stale/unsafe and is
not killed automatically.

### Parser progress

Keep the current recursive-descent parser. Add a single invariant to every
collection loop: each successful iteration must consume input or terminate.
Unexpected closing delimiters, empty barewords, and EOF inside an open list or
tuple raise `MIParseError` with the current position. Do not add recovery that
invents structure. Validate against the existing real MI fixtures before
expanding the malformed corpus.

### Installer trust chain

Keep `pipx`, but separate four stages:

1. fetch and validate a bounded manifest;
2. download a bounded GitHub Release wheel into private temporary storage;
3. verify required SHA-256 and expected wheel/project/version identity;
4. give only the verified local path to `pipx install` or `pipx upgrade`.

Remote manifests and redirect destinations must use HTTPS and the project-owned
GitHub repository/release host policy. Local `file:` and checkout overrides
remain available only through the explicit local installer path and are clearly
reported as local trust decisions. The manifest schema adds the artifact hash,
artifact kind, and optional size. Unknown fields may be tolerated only if the
schema policy says so; unknown schema versions fail closed.

Use `packaging.version.Version` and `packaging.specifiers.SpecifierSet` through
one internal versioning module. Adding `packaging` as a runtime dependency
requires the repository's dependency review: exact problem, standard-library
gap, license, security, maintenance, transitive footprint, deterministic impact,
and rejected alternatives. Pin the selected audited release consistently with
the existing runtime dependency policy.

### Release artifact identity

The install source becomes a project-owned GitHub Release wheel, not the
self-referential Git tag tarball. Build with a fixed `SOURCE_DATE_EPOCH` derived
from the documented release date, not from a commit that changes when the hash
is recorded. Build twice in clean environments and require identical wheel
hashes. Record that hash in the release manifest. Rebuild after the manifest
commit with the same epoch and require the wheel hash to stay identical. The
wheel tested by the fresh-install smoke is the wheel uploaded to the release.

## PR 1 — Build, CI, and Clean-Clone Reproducibility

### Files / modules

- `pyproject.toml`
- `.github/workflows/quality-and-traceability.yml`
- `scripts/verify-release.sh` (new)
- `tests/test_release_verification_script.py` (new)
- `tests/test_verify_workflow_docs.py`
- `tests/test_release_version_metadata.py`
- `README.md`
- contributor/release workflow documentation as required

### Steps

1. Add a failing isolated-build regression that captures the current Setuptools
   metadata error.
2. Remove the superseded license classifier while retaining the SPDX license
   expression and license file in distributions.
3. Initialize recursive submodules in CI and fail if `git submodule status
   --recursive` contains uninitialized or mismatched entries.
4. Update clone/onboarding instructions with `--recurse-submodules` and the
   recovery command for an existing clone.
5. Split CI responsibilities:
   - quality/type/coverage on Python 3.12;
   - non-HIL compatibility tests across every claimed Python minor;
   - artifact build and fresh-wheel smoke on Python 3.12.
6. If a claimed Python minor fails, fix a bounded compatibility defect or narrow
   `requires-python`; do not label a failing version supported.
7. Add `scripts/verify-release.sh` to check submodules, run the authoritative
   full gate, build wheel/sdist, run `twine check`, install the wheel into a
   temporary venv, and smoke the real `dbgoracle` entrypoint.
8. Ensure the script accepts no destructive broad path and always uses a fresh
   temporary directory with cleanup.
9. Measure full-gate duration with initialized fixtures. Keep the existing CI
   timeout only if it has adequate headroom; otherwise update the timeout and
   its contract test with evidence.

### Exit gate

- AC-001 through AC-004 pass in a fresh recursive clone.
- The built wheel contains `LICENSE`, package modules, and entry-point metadata,
  and excludes tests, private notes, caches, local artifacts, and `.git` data.

## PR 2 — Evidence Write, Parser, and Process Safety

### Files / modules

- `debugoracle/safe_io.py` (new)
- `debugoracle/artifacts/repository.py`
- `debugoracle/pipeline/storage.py`
- `debugoracle/sources/streams/rtt.py`
- `debugoracle/cli/commands/evidence.py`
- `debugoracle/cli/commands/status_capture.py`
- `debugoracle/cli/commands/run_stop.py`
- selected `init_workspace.py` or docs-sidecar call sites only after classification
- `debugoracle/mi.py`
- `tests/test_safe_io.py` (new)
- `tests/test_artifact_schema.py`
- `tests/test_rtt_capture.py`
- `tests/test_run_stop.py`
- `tests/test_mi_parse.py`
- CLI integration tests for error mapping

### Steps

1. Write sentinel-based adversarial tests for symlink final targets, symlink
   parents, outside-workspace escapes, existing regular files, concurrent parent
   replacement, and explicit outside output.
2. Implement descriptor-relative safe directory traversal and atomic writes.
3. Migrate canonical JSON and explicit render output sites one at a time; run
   their nearest tests after each migration.
4. Open RTT and run logs with no-follow flags and preserve append/truncate
   semantics for safe regular files.
5. Inject short writes, flush failures, replace failures, and ENOSPC-like errors;
   prove that prior canonical state remains loadable.
6. Add malformed MI cases first, including mismatched braces/brackets, empty
   items, truncated strings, nested invalid closers, and large bounded nesting.
7. Enforce parser progress and controlled delimiter errors without changing
   valid fixture output.
8. Version run metadata, capture Linux process start time, and implement exact
   identity validation.
9. Recheck identity immediately before SIGTERM and SIGKILL. Add a deterministic
   fake `/proc` seam for tests; use a real subprocess integration test for the
   positive stop path.
10. Document any deliberate compatibility change for legacy runtime metadata.

### Exit gate

- AC-005 through AC-010 and AC-024 pass.
- Security review finds no high/critical unresolved filesystem or signaling
  issue.
- Snapshot/report determinism fixtures remain unchanged unless the spec requires
  a warning-only change.

## PR 3 — Installer Trust, Recovery, and Version Semantics

### Files / modules

- `pyproject.toml`
- `debugoracle/installer/manifest.py`
- `debugoracle/installer/core.py`
- `debugoracle/installer/backend/pipx.py`
- `debugoracle/installer/versioning.py` (new)
- `debugoracle/installer/source.py` (new, if separation stays small)
- `debugoracle/installer/outcomes.py`
- `release/install-manifest.json` schema fields, using non-release fixture values
- installer unit/integration tests
- `docs/specs/install_cli.md`
- dependency audit artifact for `packaging`

### Steps

1. Add table-driven failing tests for PEP 440 ordering and specifiers, including
   `0.2.0rc1 < 0.2.0 < 0.2.1`, dev/post/local/epoch values, and invalid versions.
2. Introduce one versioning implementation and delete duplicated normalization.
3. Complete the runtime dependency review before adding/pinning `packaging`.
4. Version the release manifest schema and validate required identity, URL,
   checksum, artifact kind, size, and supported Python range.
5. Add bounded HTTPS fetch with redirect validation and response-size limits.
6. Download to private temporary storage, hash while reading, validate size and
   wheel filename/project/version, then install only the local verified file.
7. Preserve the current installation on download, checksum, or pipx failure and
   clean all temporary files. A fresh install whose post-install inspection
   fails is removed. For an upgrade whose pipx mutation succeeded but whose
   inspection then fails, return `state unknown`, perform no further mutation,
   and provide manual recovery steps; an exact automatic rollback would require
   a separately retained and hashed prior-version artifact and must not fall
   back to an unbound package requirement.
8. Catch post-install `inspect_installation` failures and return a specific
   deterministic outcome with remediation text.
9. Keep checkout-local overrides explicit and test that they cannot be selected
   by a remote manifest.
10. Run install/upgrade/uninstall tests against a fake pipx contract, then a real
    disposable pipx home in integration testing.

### Exit gate

- AC-011 through AC-014 pass.
- Dependency license/security audit is recorded.
- Security review approves the remote execution boundary.

## PR 4 — CLI Contract and Documentation Synchronization

### Files / modules

- `debugoracle/cli/commands/evidence.py`
- CLI argument construction in `debugoracle/cli/main.py`
- `tests/test_cli_flow.py`
- `tests/test_cli_live.py`
- `tests/test_docs_cli_and_status_capture.py`
- `docs/specs/cli.md`
- `docs/specs/docs_cli.md`
- `docs/specs/testing-contracts.md`
- `README.md`
- relevant installation/workspace/vendor-document guides
- `changelog.md` under `Unreleased`

### Steps

1. Add exact subprocess tests for stdout, stderr, and exit codes before changing
   implementation.
2. Return exit `2` for no valid input under the selected fetch mode.
3. Render partial-evidence warnings once on stderr while preserving structured
   snapshot warnings and clean stdout.
4. Add a reusable argparse port validator for `1..65535` and apply it to all
   applicable TCP port arguments.
5. Verify that controlled parse/safe-path/connection failures have actionable
   stderr and no traceback.
6. Remove the stale `docs search --semantic` contract, add omitted `docs doctor`
   references, replace the stale schema number, and consolidate the duplicate
   `init-workspace` description around actual `--auto` behavior.
7. State clearly that optional Docling/semantic installer profiles remain
   blocked; do not instruct users to select unavailable supported profiles.
8. Re-run help/reference comparison tests so every documented flag and command
   is backed by parser output.

### Exit gate

- AC-015 through AC-018 pass.
- Full CLI QA outcome is `PASS`, with no contract blocker and byte-identical
  deterministic report checks.
- Documentation release review reports `docs_sync: complete` for implemented
  behavior, leaving release-version material under `Unreleased`.

## PR 5 — Provenance Closure and Release Candidate

### Files / modules

- retained third-party license/notice/receipt files or removal diff
- `THIRD_PARTY_NOTICES.md`
- `docs/audits/public-alpha-p0-release-inventory.md` or a new immutable release audit
- `debugoracle/version.py`
- `release/install-manifest.json`
- `tests/test_release_version_metadata.py`
- `tests/test_public_release_contract.py`
- `SECURITY.md`
- `changelog.md`
- README/platform support text
- release checklist/evidence report

### Steps

1. Resolve each provenance gap with primary acquisition evidence, version/commit,
   archive hash, and license/notice. If evidence cannot be obtained, remove the
   component and update demos/tests/docs in the same PR.
2. Recursively verify Pico SDK and nested submodules at pinned commits; record
   their license/notice closure and ensure no unexpected dirty content exists.
3. Confirm remotely that `v0.3.0` is unused. Freeze the candidate version.
4. Move `Unreleased` entries into a dated `0.3.0` section describing shipped
   behavior, compatibility, and security fixes rather than intent.
5. Synchronize canonical version, SECURITY support table, manifest identity,
   release URLs, tests, and documentation.
6. Build the wheel twice from the candidate commit with fixed build inputs and
   compare SHA-256. Investigate any difference before proceeding.
7. Record the tested wheel's URL, size, kind, and hash in the manifest. Rebuild
   and prove that package bytes remain identical because release metadata is not
   included in the wheel payload; otherwise redesign the two-stage procedure.
8. Run `scripts/verify-release.sh` in a fresh recursive clone and retain its
   concise evidence report.
9. Perform sanitized manual/HIL checks on Ubuntu 24.04 x86-64, Python 3.12, and
   the supported embedded reference setup.
10. Run final review, CLI QA, security review, dependency audit, document-release,
    and ship gates. Resolve every critical/high finding and explicitly disposition
    remaining lower-severity items.
11. Create an annotated tag only after all gates pass; sign it when the
    maintainer's established signing identity is available, otherwise record the
    exact GitHub commit SHA and the absence of tag signing in the release
    evidence. Upload exactly the tested wheel, sdist, checksums, and release
    notes. Verify downloaded asset hashes and perform one final clean install
    from the public URL.

### Exit gate

- AC-019 through AC-024 pass.
- Release status is `ready`, not `blocked` or `review`.
- The public asset downloaded after publication is byte-identical to the tested
  asset.

## Acceptance Criteria -> Validation Map

| AC ID | Validation type | Location / command |
|---|---|---|
| AC-001 | integration | `python -m build` in release verification script |
| AC-002 | integration | `twine check dist/*`; fresh-wheel venv smoke |
| AC-003 | regression | CI workflow tests; fresh recursive clone full gate |
| AC-004 | compatibility | CI Python-minor matrix |
| AC-005 | adversarial unit/integration | `tests/test_safe_io.py` outside sentinel tests |
| AC-006 | failure-injection | safe I/O, artifact, RTT, and run metadata tests |
| AC-007 | adversarial integration | `tests/test_rtt_capture.py` symlink/append/truncate cases |
| AC-008 | regression | `tests/test_mi_parse.py`; bounded timeout wrapper |
| AC-009 | unit/integration | `tests/test_run_stop.py` fake `/proc` and real subprocess |
| AC-010 | negative integration | missing/denied/malformed `/proc` cases |
| AC-011 | security unit | manifest URL/redirect/size/schema table tests |
| AC-012 | security integration | checksum mismatch, cleanup, unchanged pipx state |
| AC-013 | unit | PEP 440 version/specifier table tests |
| AC-014 | failure-injection | installer backend and post-inspection failures |
| AC-015 | subprocess contract | focused `fetch` no-input CLI test |
| AC-016 | subprocess contract | stdout/stderr/snapshot warning assertions |
| AC-017 | parser contract | invalid boundary ports across applicable commands |
| AC-018 | regression/manual | help-vs-doc tests plus document-release review |
| AC-019 | audit/manual gate | release inventory, hashes, licenses, recursive status |
| AC-020 | regression | release metadata consistency tests |
| AC-021 | integration/manual | download public asset, hash, fresh pipx install |
| AC-022 | aggregate gate | `./scripts/verify.sh full`; all review/QA skills |
| AC-023 | HIL/manual | signed sanitized release checklist |
| AC-024 | failure-injection | cross-area recovery test matrix |

## Validation Commands

Use exact commands defined by the implementation. The final expected sequence is:

```bash
git submodule update --init --recursive
git submodule status --recursive
./scripts/verify.sh fast
./scripts/verify.sh full
./scripts/verify-release.sh
pre-commit run --all-files
```

Also run the focused suites listed in the test plan after their corresponding
PR. Never use a passed focused suite as a substitute for the full gate.

## Release / Compatibility Notes

- Correcting `fetch` exit code and stderr warnings restores an existing public
  specification; it is still a user-visible behavior change and requires
  changelog coverage.
- Unsafe symlink and legacy runtime-control paths will fail closed. Document the
  error and recovery action instead of silently retaining unsafe compatibility.
- Snapshot schema remains unchanged.
- Installer manifest schema changes are versioned. Checkout-local installation
  remains available, while remote install sources become hash-bound release
  assets.
- Support claims follow tested evidence. If Python 3.10 through 3.14 do not all
  pass, narrow `requires-python` and README/SECURITY consistently.
- Narrowing hardware claims because HIL is unavailable is a scope change: update
  the task spec and rerun the engineering plan review before implementation.

## Definition of Done

The work is done only when every AC is evidenced, no release-blocking provenance
gap remains, no critical/high security finding remains, the built public asset
matches the tested hash, manual verified-environment checks are recorded, and
the ship gate says `release status: ready`.
