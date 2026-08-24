# Public Release Hardening Task Spec

**Status:** Implemented; external release gates remain open

## Problem Statement

DebugOracle's non-HIL implementation passes the repository's authoritative
quality gate when all recursive submodules are initialized, but the current
tree is not releasable. A clean package build fails, a normal clone does not
contain the reference-workspace fixtures required by the test suite, historical
release metadata still points at the withdrawn private `v0.2.0`, and the
repository's own provenance audit still contains public-export blockers.

Release QA also found trust-boundary and contract defects: workspace-derived
outputs follow symlinks, several canonical JSON files are written non-atomically,
one malformed GDB/MI record can make the parser stop making progress, `stop`
does not bind a PID strongly enough to the process that created the runtime
metadata, installer sources are not cryptographically bound to a manifest,
installer version comparisons are not PEP 440 compliant, and two documented
`fetch` behaviors are not implemented.

The task is to close those defects without changing DebugOracle's five-stage
pipeline or adding product features, then produce auditable evidence that the
result can be published as the next public alpha.

## Release Target

- Working release version: `0.3.0`.
- Release channel: GitHub Release plus the supported Linux `pipx` installer.
- PyPI publication is not part of this task.
- If `v0.3.0` already exists remotely when implementation starts, stop and
  select a new unused PEP 440 version before changing release metadata.
- The supported environment remains Linux. The package's declared Python
  range must be tested, narrowed, or corrected before release.

### Temporary CI deviation

On 2026-08-24 the maintainer deferred publication of the private
`nikolasvoss/debugoracle-reference-workspaces` repository. Pull-request and
`main` CI therefore omit its checkout and the tests that require its contents.
This is not evidence for AC-003: tag validation remains fail-closed, requires
the complete recursive checkout, and blocks publication until the reference
repository is publicly readable or an equivalent reviewed distribution is
provided. The follow-up is tracked in `ROADMAP.md`.

## Scope

### In scope

- Restore isolated wheel and sdist builds with current declared build tooling.
- Make recursive submodule initialization explicit in onboarding and CI.
- Add a release-artifact gate: build, metadata validation, fresh-wheel install,
  CLI smoke tests, and release-metadata consistency checks.
- Test every Python minor version claimed by `requires-python`, or narrow the
  claim to the versions that pass.
- Introduce a centralized, POSIX-safe write boundary for workspace-derived and
  explicit CLI output paths.
- Prevent symlink traversal and target replacement for automatically derived
  workspace outputs.
- Make canonical snapshot, state, and runtime metadata writes atomic.
- Preserve the streaming nature of RTT logs while opening them without
  following symlinks and without silently truncating an unintended target.
- Make GDB/MI parsing fail with `MIParseError` whenever parsing cannot advance.
- Bind `stop` to the exact Linux process instance recorded by `run`, including
  `/proc` start time and exact expected argv/workspace checks.
- Replace duplicated ad-hoc version comparison with one PEP 440 implementation.
- Restrict remote installer manifests and sources to authenticated HTTPS,
  bounded payloads, allowlisted package/repository identity, and a required
  SHA-256 for the install artifact.
- Convert installer post-install inspection failures into structured outcomes.
- Correct `fetch` exit-code and warning-stream behavior to match the existing
  CLI specification.
- Reject invalid network port values during argument parsing.
- Resolve release-relevant README, CLI, docs, schema-version, and optional
  tooling documentation drift.
- Close or remove every public-export blocker in the retained third-party
  inventory.
- Synchronize version, changelog, manifest, support policy, tests, and release
  URLs for the selected release.
- Run the required code review, CLI QA, security review, documentation release
  gate, and final ship gate.

### Out of scope

- New debugger backends, transports, report formats, or evidence types.
- Changes to the Acquire -> Normalize -> Reduce -> Persist -> Render model.
- Artifact schema changes unrelated to fixing incorrect documentation.
- Windows or macOS support.
- Enabling the currently blocked Docling, semantic, or combined installer
  profiles; documentation must describe their actual state instead.
- A general filesystem abstraction for non-DebugOracle applications.
- Publishing to PyPI.
- Broad refactors of parsing, rendering, discovery, or installer architecture.
- Weakening tests, coverage, Bandit, type checking, or HIL exclusions to make a
  gate pass.

## Invariants Touched

- **Deterministic:** parser rejection and serialized output remain stable;
  ordering and JSON formatting do not change except where a documented warning
  or error code is corrected.
- **Evidence-first:** malformed or partial evidence is either retained with
  explicit warnings or rejected with a traceable parse error; it is never
  silently inferred.
- **Read-only target behavior:** no change may write to debugger or target
  memory. Filesystem hardening only affects host-side DebugOracle outputs.
- **Reproducible:** package artifacts, submodule state, test inputs, release
  metadata, and dependency provenance are explicit.
- **Explicit provenance:** released third-party files and install artifacts have
  traceable origin, license evidence, version, and hash.
- **Data integrity:** canonical JSON state is published atomically; a failed
  write leaves either the prior complete version or no new version.
- **CLI separation:** stdout remains the primary result and warnings/errors use
  stderr.

## Acceptance Criteria

- **AC-001:** `python -m build` produces one sdist and one wheel in a clean,
  isolated environment using the declared build requirements.
- **AC-002:** `twine check` passes for every built distribution and a clean venv
  can install the wheel and execute `dbgoracle --version` and top-level help.
- **AC-003:** CI initializes every recursive submodule, rejects missing or
  mismatched gitlinks, and the full non-HIL gate passes from a fresh clone.
- **AC-004:** CI tests all Python minor versions admitted by
  `requires-python`; unsupported versions are explicitly excluded in metadata
  and documentation.
- **AC-005:** automatically derived workspace output paths reject symlink files,
  symlink directories, path escapes, and parent replacement attempts without
  modifying an outside sentinel file.
- **AC-006:** canonical snapshots, RTT state, and run metadata use same-directory
  temporary files, flush/fsync, and atomic replacement; injected write failures
  preserve the prior complete file.
- **AC-007:** RTT create/truncate/append opens the final file without following
  symlinks and reports a controlled non-zero outcome for unsafe paths.
- **AC-008:** every bounded malformed GDB/MI fixture, including
  `^done,result=[}]`, returns or raises a controlled parse error without a hang;
  valid fixtures retain their current parsed structure.
- **AC-009:** `stop` sends no signal unless PID, `/proc` start time, executable,
  exact argv shape, and canonical workspace identity match the recorded run;
  identity is rechecked before every signal escalation.
- **AC-010:** missing or inaccessible `/proc` identity evidence fails closed and
  produces an actionable, structured `stop` result.
- **AC-011:** installer manifest retrieval rejects plain HTTP, oversized
  payloads, unexpected redirect destinations, unknown package identity, and
  unsupported schema versions.
- **AC-012:** remote installation verifies the exact SHA-256 of a bounded
  release asset before passing a local verified file to `pipx`; mismatch leaves
  the existing installation unchanged and removes staging files.
- **AC-013:** version and specifier handling is centralized and PEP 440 correct
  for final, rc, dev, post, local, and epoch versions.
- **AC-014:** all installer backend and post-install inspection failures map to
  deterministic structured outcomes without tracebacks.
- **AC-015:** `fetch` with no valid input source returns exit code `2` and an
  actionable stderr message.
- **AC-016:** partial-evidence `fetch` runs return `0`, retain structured warning
  events, and emit the same warning meaning immediately on stderr without
  contaminating stdout.
- **AC-017:** TCP ports outside `1..65535` are rejected at argument parsing with
  exit code `2` and without attempting a connection.
- **AC-018:** release-facing documentation matches the implemented command set,
  options, schema version, submodule setup, optional-tooling availability, and
  verified compatibility matrix.
- **AC-019:** every retained STM32, CMSIS, HAL, SVD, Pico SDK, and nested
  submodule component has recorded origin, pinned version/commit, license or
  notice evidence, and acquisition hash; unresolved components are removed
  from the release scope and all references/tests are updated accordingly.
- **AC-020:** canonical version, tag, changelog section, installer manifest,
  release URLs, security support table, package metadata, and version tests all
  agree on the selected release.
- **AC-021:** the manifest install asset is a GitHub Release asset owned by this
  project, matches the recorded SHA-256, and is the same wheel that passed the
  fresh-install smoke test.
- **AC-022:** the authoritative full gate, focused adversarial suites, CLI QA,
  security review, docs-release review, dependency vulnerability audit, and
  release-artifact gate all pass with no critical/high unresolved finding.
- **AC-023:** manual verified-environment checks cover fresh install, upgrade,
  uninstall, successful RTT capture, detached run/stop, OpenOCD discovery,
  SVD register capture, and bounded memory read, with sanitized evidence saved.
- **AC-024:** interruption, ENOSPC/write-failure, malformed input, connection
  timeout, checksum mismatch, and stale PID scenarios produce controlled
  outcomes and leave recoverable state.

## External Evidence Gate

Implementation may begin before third-party provenance is complete, but a
release candidate may not be tagged until AC-019 is closed. The preferred path
is to obtain and retain the exact upstream package license and acquisition
receipt. If that cannot be done, remove the blocked assets and narrow the demo
and documentation rather than inferring permission.

## Risks

- Technical risk: low-level no-follow and atomic-write code can introduce
  portability or permissions regressions if call sites are migrated blindly.
- Security risk: path validation without descriptor-relative operations can
  retain TOCTOU races.
- Data risk: changing runtime metadata can make old detached sessions
  un-stoppable unless the compatibility behavior is explicit.
- Release risk: hashing a mutable tag archive or allowing a manifest to change
  both URL and hash does not create a meaningful source binding.
- Legal risk: provenance notes are not a substitute for the referenced license
  or acquisition receipt.
- Operational risk: a Python matrix can expose unsupported versions late; the
  metadata must fail closed rather than retain an untested broad range.

## Rollback Plan

- Land the work as five sequential PRs described in the implementation plan.
- Each PR must be independently revertible and must preserve the current
  snapshot schema.
- Safe-write and runtime-metadata changes retain read compatibility for existing
  canonical artifacts; runtime control metadata may use a versioned schema and
  must fail closed on older unsafe records.
- Installer manifest/schema changes must reject unknown remote schemas while
  preserving checkout-local installation through an explicit local override.
- If a release-candidate check fails, do not move or reuse the tag. Fix on a new
  commit, rebuild all artifacts, recompute hashes, and create the tag only after
  the gate passes.
- If a published asset differs from the tested hash, withdraw that release and
  issue a new version; never replace an immutable released artifact in place.
