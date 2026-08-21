# Public Alpha P0 Risk Register

**Status:** Closed for `v0.2.0` with accepted residual risks — 2026-08-21

## Final Risk Disposition

The mandatory code, CLI-QA, security, documentation, and ship gates completed
without an unresolved Critical or High implementation finding. High-risk parser
and sidecar-path findings discovered during review were fixed before release.

The owner accepted the following release-level exceptions with their
uncertainty kept explicit:

- Existing reviewed repositories were published instead of the planned new
  clean-history exports (R-001, R-015, R-017 process deviation).
- Exact package/acquisition provenance for retained STM32 generated material and
  the SVD remains incomplete (R-003); no verified-origin claim is made.
- The optional video/animation was deferred while the reproducible text/static
  demo shipped (R-010).
- Optional Docling and semantic profiles remain disabled (R-005).

The automatic-initialization security audit also retains three non-blocking
Medium risks: same-user filesystem TOCTOU, in-process PDF resource isolation,
and recoverable but non-transactional multi-file scaffold writes. See
`../audits/automatic-workspace-init-security-review.md` for the final evidence.

## Risk Tier

Overall tier: **High**. Private-to-public publication, third-party licensing,
debug-artifact sensitivity, installer mutation, and irreversible external
distribution require `/security-review` before publication.

| ID | Risk | Tier | Mitigation | Release evidence / trigger |
|---|---|---:|---|---|
| R-001 | Secret, private data, or internal GitHub content becomes public | High | Use new clean repositories; audit exported files and do not migrate private history or GitHub artifacts | Security review and candidate object/ref inventory contain no unresolved finding |
| R-002 | Vendor manuals or extracted derivatives are redistributed without permission | High | Remove ST/SEGGER PDFs, sidecars, embeddings, and extracted indexes; link official sources | Public contract finds none; clean candidates are size/path reviewed |
| R-003 | Generated STM32 code lacks its governing package license | High | Record exact STM32Cube origin/version and include component-root license plus retained headers | Provenance inventory maps every generated tree to its source and terms |
| R-004 | Apache-2.0 distribution retains an AGPL PDF dependency | High | Remove PyMuPDF/PyMuPDF4LLM dependency, imports, help, and fallback paths; use BSD-3-Clause pypdf | Dependency/import contract passes and clean environment inspection confirms absence |
| R-005 | Optional Docling dependency or model introduces unresolved terms | High | Audit optional dependency/model inventory; disable the optional profile if unresolved | Complete inventory, or profile is excluded from `0.2.0` installer/docs |
| R-006 | Required public workflow depends on private HIL or reference content | High | Remove HIL from public dependency graph; publish clean reference repository first and pin it | Anonymous recursive clone succeeds without credentials |
| R-007 | Debug artifacts disclose usernames, paths, symbols, memory, or proprietary evidence when shared | High | Sanitize shipped fixtures; state local-processing boundary and review-before-sharing warning | Path/privacy contract plus README/security review |
| R-008 | pypdf produces materially poorer or misleading document evidence | Medium | Preserve explicit quality states, page provenance, warnings, and optional audited Docling path; test representative PDFs | Parser quality tests and no unsupported clean result for empty/scanned pages |
| R-009 | Parser migration corrupts or silently reuses stale sidecars | Medium | Include parser in freshness contract; document re-ingestion; preserve schema compatibility | Freshness and legacy-sidecar regression tests pass |
| R-010 | Demo is persuasive but not reproducible | Medium | Drive video and transcript from one checked-in sanitized fixture and exact commands | Two-run deterministic integration test matches transcript |
| R-011 | README or demo overclaims diagnosis, compatibility, or write capability | Medium | Evidence/hypothesis separation; tested-versus-unverified matrix; remove absolute guarantees | Manual product review and prohibited-claim contract pass |
| R-012 | Release metadata drifts and checkout installation verifies the wrong version | Medium | Canonical version source; manifest/changelog/tag regression; immutable tags | Metadata test and installed CLI report `0.2.0` |
| R-013 | Moving `ubuntu-latest` or undeclared host differences make validation irreproducible | Medium | Pin Ubuntu 24.04 and Python 3.12; validate in isolated clean environment | CI configuration and clean-host transcript |
| R-014 | Installer QA mutates the maintainer's real environment | Medium | Run install/uninstall acceptance in disposable VM/container or isolated user paths | Test transcript identifies disposable environment and cleanup |
| R-015 | Current unrelated work is mixed into the release branch | Medium | Resolve current dirty main/submodule state first; create a dedicated release branch | Release diff contains only task-spec scope |
| R-016 | Clean-history export accidentally omits a required source/test/license file | Medium | Public allowlist/contract checks, build/install/full validation in candidate clone | Candidate passes package build, install, demo, and full validation |
| R-017 | Public repository is enabled before all gates pass | High | Owner-only visibility/publication step at `/ship`; publication is never a test step | Signed release checklist shows all prior gates complete |
| R-018 | Sensitive content is discovered after publication | Critical | Rotate/revoke secrets immediately, assess forks/clones, remove affected release, and engage GitHub support; prevention remains primary | Incident procedure invoked; release cannot be considered recoverably private |

## Required Downstream Stages

1. `/cli-qa`
2. `./scripts/verify.sh full`
3. `/review`
4. `/security-review` — mandatory
5. `/document-release`
6. `/ship`

No repository may be made public while a High or Critical risk has an unresolved
release trigger.
