# Public Alpha P0 Task Spec

**Status:** Closed with accepted deviations — private `v0.2.0` withdrawn before public availability

## Release Disposition

This specification is retained as the historical contract that drove the
public-alpha work. The private release was withdrawn before public availability;
a future release must use a newly selected version. The core user outcome is
ready for a future release: an anonymous user can install
the base CLI, open the bundled reference workspace, initialize and query the
project-owned documentation, and inspect deterministic snapshot/register/source
evidence without an embedded toolchain, probe, board, or vendor PDF.

Acceptance criteria for licensing surfaces, prohibited assets, pypdf behavior,
metadata consistency, automatic initialization, documentation placement,
determinism, CLI QA, review, security review, and full validation have automated
or recorded evidence in `tests/` and `docs/audits/`.

The owner accepted these departures from the original contract at publication:

- Existing reviewed public repositories were used instead of replacement
  clean-history repositories, so the clean-history portion of AC-013 was not
  executed as written.
- The copyable fixture and static/text showcase satisfy the reproducible demo
  goal, but the optional video or animation was deferred.
- Package-level acquisition evidence for retained STM32 generated material and
  exact upstream acquisition evidence for the SVD remain incomplete. Shipped
  documentation preserves this uncertainty and does not infer provenance.
- Optional Docling, semantic, and combined installer profiles remain disabled
  pending complete dependency and model-license evidence.

These are release-record exceptions, not changes to the evidence-first,
read-only, deterministic product invariants below.

## Problem Statement

DebugOracle is implemented and validated as a private engineering project, but
its current repository state is not safe or useful enough for a public
open-source alpha. The repositories contain redistributable and uncertain
third-party material, generated documentation sidecars, machine-specific paths,
an AGPL PDF dependency, private/optional submodule coupling, incomplete public
governance, inconsistent release metadata, and no short reproducible public
demonstration.

The release must let an unfamiliar embedded developer understand and exercise
one trustworthy DebugOracle workflow without weakening the acquire, normalize,
reduce, persist, and render pipeline.

## Scope

### In scope

- License DebugOracle-owned source under Apache-2.0.
- Add a security policy that uses GitHub private vulnerability reporting and
  does not publish a maintainer email address.
- Create clean-history public repositories from audited snapshots while
  retaining the current private repositories as archives.
- Publish the reference-workspaces repository and point the public DebugOracle
  repository at its public pinned commit.
- Exclude the private HIL repository from all public clone, validation, install,
  and demo requirements.
- Remove vendor PDFs and generated `*.dbgoracle-docs/` sidecars from the public
  repositories and replace the manuals with official vendor download links.
- Retain generated STM32 firmware only with the exact originating package
  license, preserved file notices, package version, and source provenance.
- Preserve Apache-2.0 STM32 SVD and CMSIS content and BSD-3-Clause STM32 HAL
  content with their notices.
- Replace mandatory `pymupdf` and `pymupdf4llm` use with a BSD-3-Clause `pypdf`
  parser while preserving the docs-sidecar schema and parser boundary.
- Retain Docling as optional tooling only after its direct dependencies and
  model licenses are recorded as compatible with the release policy.
- Support and test the alpha on Ubuntu 24.04 LTS x86-64, Python 3.12, and
  `pipx`; describe other environments as unverified.
- Release version `0.2.0` with one canonical version source and enforced
  agreement among CLI, package, manifest, changelog, and tag.
- Provide a short video or animation plus a copyable, deterministic,
  hardware-free demonstration of an evidence-backed agent answer.
- State that DebugOracle processes local files but users must review artifacts
  before sharing them with agents, issue trackers, or other people.

### Out of scope

- Publishing the HIL repository.
- PyPI publication or Trusted Publishing.
- Windows or macOS support.
- Broad Linux distribution or Python-version compatibility claims.
- Redaction implementation or telemetry.
- Serial capture, MCP, session history, autonomous debugging, or target writes.
- Changes to snapshot schemas or the acquire/normalize/reduce/persist/render
  architecture.
- A documentation website or mature community-governance program.
- Rewriting the history of the private archive repositories.

## Invariants Touched

- **Determinism:** pypdf parsing and the hardware-free demo must produce stable,
  ordered results for identical inputs.
- **Evidence-first:** the demonstration must distinguish captured evidence,
  structural interpretation, hypothesis, and missing evidence.
- **Read-only:** no release or parser change may add target mutation.
- **Reproducibility:** a clean anonymous clone must install and run the demo in
  the declared environment.
- **Explicit provenance:** document pages, generated STM32 files, SVD data, and
  third-party source trees must retain traceable origins and licenses.
- **Privacy boundary:** DebugOracle remains local-first; documentation must not
  imply that local storage makes externally shared artifacts safe.

## Acceptance Criteria

- **AC-001:** The public main repository contains an Apache-2.0 `LICENSE`, a
  `SECURITY.md` that points exclusively to GitHub private vulnerability
  reporting, and a complete third-party notice/provenance inventory.
- **AC-002:** No vendor PDF, generated docs sidecar, embedding file, or extracted
  vendor-manual index exists in either public repository, and ignore rules
  reject future `*.dbgoracle-docs/` directories.
- **AC-003:** All generated STM32 content retained for public examples has its
  exact originating package license, version, source URL, and existing file
  notices preserved.
- **AC-004:** An anonymous recursive clone of the public main repository resolves
  every required submodule at a pinned public commit; HIL is absent from the
  required dependency graph.
- **AC-005:** Base installation contains no `pymupdf` or `pymupdf4llm`
  dependency or import, and `pypdf` is the default PDF parser.
- **AC-006:** pypdf ingestion preserves stable page provenance, deterministic
  page order, explicit empty/unreadable-page outcomes, and the existing
  docs-sidecar envelope/storage schema.
- **AC-007:** Docling fallback uses pypdf, reports the selected/fallback parser
  explicitly, and no optional dependency or model with an unresolved license is
  selected by the supported installer.
- **AC-008:** CI is pinned to Ubuntu 24.04 and Python 3.12, and the README clearly
  separates the tested alpha environment from unverified environments.
- **AC-009:** `debugoracle.version.__version__`, package metadata,
  `dbgoracle --version`, the install manifest, the newest changelog release, and
  tag `v0.2.0` agree.
- **AC-010:** A clean installation can execute the hardware-free demo without a
  probe, target, OpenOCD session, network fetch, or vendor PDF and produces the
  documented evidence and next direction deterministically.
- **AC-011:** The first README screen states the user problem, shows the short
  demo, links to a text transcript, names the tested environment, and explains
  trust and limitations before internal contributor workflow.
- **AC-012:** Public docs, fixtures, screenshots, expected artifacts, and links
  contain no maintainer-home absolute paths, stale `DebugAssist` branding,
  unsupported “no hallucination” guarantee, or controlled-write promise.
- **AC-013:** The public repositories start from audited clean snapshots; the
  private repositories remain private archives; no old private history, branch,
  Actions artifact, issue, or pull request is copied to the public repositories.
- **AC-014:** Targeted tests, CLI QA, `./scripts/verify.sh full`, `/review`, and
  the mandatory `/security-review` all pass before any repository is made
  public.

## Risks

- **Technical risk:** pypdf may extract complex tables or layouts less accurately
  than PyMuPDF4LLM. Existing quality states must make degradation explicit, and
  optional Docling remains the stronger path for difficult PDFs.
- **Licensing risk:** retained vendor-generated sources or optional model assets
  may have missing or incompatible terms. An unresolved item blocks publication.
- **Operational risk:** publishing is effectively irreversible once clones or
  forks exist. Public repositories must be created only from reviewed snapshots.
- **Product risk:** a video alone may look persuasive without proving that a new
  user can reproduce the result. The text demo is therefore mandatory.

## Rollback Plan

Before publication, discard the candidate public repositories and correct the
private source branches; the private archives remain authoritative and intact.
Parser changes can be reverted on the private task branch without changing the
evidence pipeline.

After publication, a normal code rollback can correct software behavior, but it
cannot reliably retract exposed source or artifacts from clones and forks. Any
credential or sensitive-data finding requires immediate rotation/revocation,
publication impact assessment, and GitHub support procedures where applicable.
This is why AC-014 is a hard pre-publication gate.
