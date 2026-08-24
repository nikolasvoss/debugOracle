# Public Release Hardening Risk Register

**Status:** Active until public release completion

| ID | Severity | Risk / evidence | Mitigation | Verification | Release disposition |
|---|---|---|---|---|---|
| R-001 | Critical operational | Distribution build fails with current Setuptools because SPDX license metadata and a superseded classifier conflict. | Remove obsolete classifier; add isolated build and wheel-install gate. | AC-001, AC-002 | Must close |
| R-002 | High security | Workspace-derived outputs can follow symlink files/directories and overwrite or truncate files outside the workspace. | Descriptor-relative no-follow traversal, atomic writers, streaming no-follow open. | AC-005 through AC-007 | Must close |
| R-003 | High data integrity | Canonical snapshot, state, and runtime JSON writes can be partial after interruption or ENOSPC. | Same-directory temp, fsync, atomic replace, failure-injection tests. | AC-006, AC-024 | Must close |
| R-004 | Medium availability | Malformed MI such as `^done,result=[}]` can make parsing stop progressing indefinitely. | Parser progress invariant and bounded malformed corpus. | AC-008 | Must close |
| R-005 | Medium/High process safety | Runtime PID metadata can identify an unrelated same-user process and `stop` can escalate to SIGKILL after a weak check. | Bind PID to `/proc` start time, exact argv/workspace, recheck before signals, fail closed. | AC-009, AC-010 | Must close |
| R-006 | High supply chain | Mutable remote manifest can direct pipx to an unverified package URL; HTTP is accepted and payloads are unbounded. | HTTPS/host/schema/size policy, release-wheel hash, local verified staging. | AC-011, AC-012, AC-021 | Must close |
| R-007 | Medium installer correctness | Ad-hoc version normalization orders rc/dev/post versions incorrectly and is duplicated. | Audited `packaging` dependency, one PEP 440 module, table-driven tests. | AC-013 | Must close |
| R-008 | Medium recovery | Post-install inspection errors escape the structured installer outcome after pipx mutation. | Catch and classify inspection failure; preserve recovery details. | AC-014, AC-024 | Must close |
| R-023 | Medium recovery | A successful pipx upgrade followed by failed inspection cannot be rolled back exactly without a separately hashed prior-version artifact. | Return deterministic `state unknown`, make no further mutation, provide manual inspection/recovery commands, and never download an unbound old requirement. Fresh-install failures are removed. | AC-014, AC-024 | Accepted residual; explicit operator recovery |
| R-009 | High contract | `fetch` no-input exit code differs from the public spec. | Restore exit 2 with subprocess contract test. | AC-015 | Must close |
| R-010 | Medium observability | Partial-evidence warnings are stored but absent from stderr, hiding degraded acquisition from agents/humans. | Central warning rendering with stdout/stderr separation tests. | AC-016 | Must close |
| R-011 | Low/Medium validation | Invalid TCP ports reach connection logic and waste timeout budget. | Argparse range validator shared by TCP commands. | AC-017 | Must close before CLI QA pass |
| R-012 | High CI/reproducibility | Normal clone and current CI omit the required reference-workspace submodule, causing 30 test failures. | PR/`main` CI temporarily report and exclude the private reference tests; tagged validation remains strict. Publish the reviewed reference repository and restore recursive CI. | AC-003 | Maintainer-deferred 2026-08-24 for non-tag CI only; blocks release tag |
| R-013 | Medium compatibility | `requires-python >=3.10` admits versions not covered by CI. | Test all admitted minors or narrow metadata and docs. | AC-004 | Must close |
| R-014 | High legal/provenance | STM32 package license, acquisition receipt, SVD origin, and recursive Pico closure remain unresolved in the public inventory. | Obtain exact evidence or remove affected assets and claims. | AC-019 | Must close; no exception |
| R-015 | High release identity | Withdrawn private `0.2.0` is still canonical and new work remains under Unreleased. | Use unused `0.3.0`, synchronize all metadata, never reuse/move tag. | AC-020 | Must close |
| R-016 | Medium documentation | CLI/docs/schema/optional-profile text has drifted from behavior. | Help-vs-doc tests and document-release gate. | AC-018 | Must close |
| R-017 | Medium artifact substitution | Built/tested wheel could differ from uploaded or manifest-referenced asset. | Repeatable build, recorded hash, download-after-publish verification. | AC-021, AC-022 | Must close |
| R-018 | Medium runtime regression | Safe-write migration could change permissions, append behavior, or explicit outside-output support. | Classify call sites; migrate incrementally; real I/O compatibility tests. | AC-005 through AC-007 | Monitor per PR |
| R-019 | Medium compatibility | Strong run metadata makes old detached sessions impossible to stop automatically. | Version metadata; fail closed with manual recovery instructions; document behavior. | AC-009, AC-010 | Accept only with documented recovery |
| R-020 | Medium release evidence | Offline tests cannot prove real RTT/OpenOCD/SVD/memory/install lifecycle. | Required sanitized HIL/manual matrix on verified environment. | AC-023 | Must close or narrow claims |
| R-021 | Low/Medium CI stability | The core coverage suite alone was observed at about 166 seconds, leaving insufficient headroom in the former three-minute quality-step timeout. | Use a five-minute quality-step timeout; retain the ten-minute artifact gate and measure the remote run. | AC-003, AC-022 | Mitigated; verify with PR CI |
| R-022 | Medium dependency governance | Adding `packaging` without the required runtime dependency review violates project policy. | Record need, alternatives, license, vulnerabilities, maintenance, footprint, determinism, and exact selected version. | AC-013, AC-022 | Must close before merge of PR 3 |

## Ownership

- Implementation owner: engineer executing the five PR sequence.
- Security sign-off: security-review gate owner, independent from the author when
  practical.
- Provenance/license sign-off: repository maintainer; agents may collect evidence
  but may not infer missing rights.
- HIL sign-off: operator with the verified hardware environment.
- Final release decision: repository maintainer after the ship gate reports
  `ready`.

## Review Cadence

- Update this register in every PR that changes a listed mitigation.
- Do not lower a severity without new evidence and a linked validation result.
- Close risks only when their mapped AC is evidenced.
- At release-candidate freeze, every remaining open row must contain an owner,
  rationale, and dated disposition; R-001 through R-017 and R-020/R-022 cannot
  be deferred.
