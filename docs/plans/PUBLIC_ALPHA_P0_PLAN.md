# Public Alpha P0 Implementation Plan

**Status:** Closed with accepted deviations — private `v0.2.0` withdrawn before public availability

## Release Outcome

This file is the historical implementation plan for the public alpha, not an
active backlog. The private `v0.2.0` tag was withdrawn before public
availability; a future release will use a newly selected version. The pinned
public reference workspace is commit `36934bd168aef6541a3c74bf6ef579b15447505c`.

The parser migration, dependency fail-closed policy, public metadata, sanitized
reference workspace, hardware-free evidence demo, automatic workspace
initialization, release contracts, CLI QA, code review, security review,
documentation gate, and full validation were completed. The following planned
items were consciously changed or deferred:

- The owner approved publication from the existing reviewed repositories rather
  than creating replacement clean-history repositories.
- The reproducible text, snapshot, PDF, and README showcase shipped without the
  optional video or animation asset.
- The public main repository is `nikolasvoss/debugOracle`, not the provisional
  `nikolasvoss/debugoracle` name in step 13.
- Optional Docling and semantic installer profiles remain disabled because their
  dependency/model license closure is incomplete.
- Exact acquisition evidence for retained STM32 generated material and the SVD
  remains incomplete; this is an explicitly accepted provenance limitation, not
  a verified origin claim.

The implementation steps below are preserved as the original execution plan.
Final evidence lives in `docs/audits/` and
`PUBLIC_ALPHA_DEMO_INIT_HANDOFF.md`.

## Purpose

Prepare a safe, reproducible, useful DebugOracle `0.2.0` public alpha from clean
repository snapshots without changing the core evidence pipeline.

## Task Link

[Public Alpha P0 Task Spec](PUBLIC_ALPHA_P0_TASK_SPEC.md)

## Preconditions

- Complete or separate the current unrelated working-tree and submodule changes.
- Create a dedicated task branch such as `release/public-alpha-p0` from the
  intended private source baseline.
- Do not change repository visibility during implementation.
- Treat the existing private repositories as archives after the public cutover;
  future public development continues in the clean public repositories.

## Architecture and Boundaries

### Unchanged product pipeline

`Acquire -> Normalize -> Reduce -> Persist -> Render` remains unchanged.
`fetch`, `report`, target transports, snapshot schemas, and trust classification
are outside this change.

### Document ingestion boundary

```text
PDF path
  -> parser factory
  -> pypdf page iterator (default) or audited Docling adapter (optional)
  -> DocsParseResult with page provenance and quality state
  -> existing chunk/index/envelope persistence
```

The parser adapter owns extraction only. Existing sidecar construction, atomic
publication, BM25/semantic search, and status rendering retain their ownership.

### Release boundary

```text
private source repositories
  -> audited release branches
  -> sanitized clean export candidates
  -> automated and manual gates
  -> new public reference repository
  -> new public main repository pinned to the public reference commit
```

No private Git history, workflow artifacts, issues, pull requests, branches, or
tags are copied into the clean public repositories.

## Files / Modules To Change

- `LICENSE` -- Apache-2.0 project license.
- `SECURITY.md` -- supported versions and GitHub private-reporting instructions.
- `THIRD_PARTY_NOTICES.md` -- component, version, source, license, and retained
  notice inventory.
- `.gitignore` -- ignore `*.dbgoracle-docs/` and their staging variants.
- `.gitmodules` -- public reference-workspace URL only; no required HIL entry in
  the public tree.
- `pyproject.toml` -- pypdf dependency and complete public package metadata.
- `debugoracle/docs_sidecar.py` -- pypdf parser adapter and Docling fallback.
- `debugoracle/diagnostics.py` -- pypdf dependency diagnostics/remediation.
- `debugoracle/cli/main.py` -- public parser choice and default.
- `debugoracle/cli/commands/docs_cli.py` -- pypdf-specific quality/help text.
- `debugoracle/version.py` -- canonical `0.2.0` release value.
- `release/install-manifest.json` -- matching `0.2.0` metadata and public URLs.
- `README.md` -- value-first alpha onboarding, demo, support boundary, privacy
  warning, and vendor-manual acquisition.
- `changelog.md` -- `[Unreleased]` plus `0.2.0` public-alpha release notes.
- `docs/docs-ingestion.md` -- pypdf default and optional Docling behavior.
- `docs/specs/docs_sidecar.md` and relevant CLI/installer specs -- new parser
  contract without changing sidecar schema.
- `.github/workflows/quality-and-traceability.yml` -- pinned Ubuntu 24.04 and
  Python 3.12 release evidence.
- `tests/test_docs_sidecar.py` -- parser and fallback behavior.
- `tests/test_diagnostics.py` -- dependency readiness behavior.
- `tests/test_release_version_metadata.py` -- version/changelog/tag contracts.
- `tests/test_public_release_contract.py` -- public-file, dependency, path,
  submodule, metadata, and prohibited-asset contracts.
- One small project-authored PDF fixture and one sanitized evidence fixture for
  the deterministic demo.
- Reference-workspace repository docs, ignore rules, license inventory,
  generated-component license roots, submodule URLs, and example assets.

## Implementation Steps

1. **Establish the release inventory.**
   Record every retained third-party component and every excluded vendor asset.
   Record the exact STM32Cube package/version that generated each retained
   firmware tree. Hash duplicate vendor assets so the removal audit is
   exhaustive.
2. **Add legal and security surfaces.**
   Add Apache-2.0, `SECURITY.md`, third-party notices, package license metadata,
   and required upstream notices. `SECURITY.md` must point to GitHub's private
   vulnerability form without publishing an email address.
3. **Sanitize the reference-workspace source.**
   Remove all ST/SEGGER PDFs, extracted sidecars, embeddings, machine-local
   links, stale generated artifacts, and optional HIL coupling. Add official
   vendor download instructions. Preserve licensed CMSIS/HAL/SVD content and add
   missing STM32 generated-component license/provenance files. Pin the public
   Pico SDK submodule commit.
4. **Replace the PDF backend.**
   Introduce the pypdf adapter behind the existing parser factory. Extract pages
   in source order, normalize text deterministically, retain page numbers, and
   translate encrypted, unreadable, image-only, and empty pages into existing
   quality/warning semantics. Remove all PyMuPDF imports and dependency/help
   text. Change Docling's explicit fallback to pypdf.
5. **Lock dependency licensing.**
   Generate a direct dependency license inventory for the base install and each
   optional profile. Do not select optional Docling/model assets in the
   supported installer until every relevant license is recorded and compatible.
   A failed audit disables that optional profile for `0.2.0`; it does not delay
   the base CLI.
6. **Align release metadata and environment.**
   Set canonical version `0.2.0`, update the manifest and changelog, expand the
   metadata regression, pin CI to Ubuntu 24.04/Python 3.12, and label all other
   environments unverified. Keep the checkout-local installer override; PyPI is
   not introduced.
7. **Build the reproducible demo.**
   Select or create a sanitized, project-owned evidence fixture. Document exact
   commands that install the CLI, build/read its snapshot, and render the
   evidence-backed direction without hardware or network access. Add stable
   assertions for the evidence, gap, and next-action lines. Record a 60-90 second
   video or animation from the same scenario and provide a text transcript and
   static fallback image.
8. **Rewrite public onboarding.**
   Lead with the observed-hardware value proposition and demo. State the tested
   stack, read-only boundary, evidence/provenance promise, known limitations,
   local-processing behavior, and sharing warning. Move contributor workflow
   below user onboarding. Replace stale DebugAssist/no-hallucination/write-access
   materials.
9. **Add public-release contract checks.**
   Reject prohibited binaries, sidecars, AGPL parser dependencies/imports,
   private submodules, absolute maintainer paths, stale branding, version drift,
   missing governance files, and broken demo paths. Keep checks structured and
   narrow rather than asserting complete documentation prose.
10. **Create the clean public reference repository candidate.**
    Export the reviewed reference tree into a new temporary directory, verify
    the allowlist/exclusions, initialize one clean history, run its documented
    checks, and prepare its public remote. Do not copy its private `.git` data.
11. **Create the clean public main repository candidate.**
    Export the reviewed main tree, point it at the candidate public reference
    commit, omit HIL, initialize one clean history, and verify anonymous clone,
    install, demo, links, and full validation.
12. **Run release gates.**
    Run targeted tests, `/cli-qa`, `./scripts/verify.sh full`, `/review`, and
    `/security-review`. Resolve every high-risk finding, then run
    `/document-release` and `/ship`.
13. **Perform owner-controlled publication.**
    Create or enable the new public repositories only after approval at the ship
    gate. Recommended public names are `nikolasvoss/debugoracle` and
    `nikolasvoss/debugoracle-reference-workspaces`. Enable private vulnerability
    reporting, required branch checks, secret scanning/push protection, and tag
    the reviewed main commit `v0.2.0`.

## Data and Failure Flow

- A missing or incompatible license blocks the affected asset. Optional Docling
  may be disabled; mandatory uncertainty blocks the release.
- A vendor PDF or sidecar found by contract checks blocks export.
- A pypdf parse failure yields the existing explicit failed/partial outcome; it
  must not silently fabricate text or switch parsers.
- Docling fallback to pypdf is explicit in `parser_used` and warning output.
- A private or unreachable required submodule blocks the clean-clone gate.
- Any version mismatch, dirty export, unexpected generated file, failed test,
  or security finding blocks tagging and publication.
- Candidate repositories may be discarded before publication. Publication is
  not used as a test step.

## Acceptance Criteria -> Validation Map

| AC ID | Validation Type | Location / Command |
|---|---|---|
| AC-001 | Contract + manual | `tests/test_public_release_contract.py`; security-policy review |
| AC-002 | Contract + export audit | prohibited-asset checks in both candidates |
| AC-003 | Manual + contract | `THIRD_PARTY_NOTICES.md`; generated-tree provenance checks |
| AC-004 | Integration | anonymous `git clone --recurse-submodules` of both candidates |
| AC-005 | Unit + contract | docs tests; dependency/import prohibition checks |
| AC-006 | Unit + replay | real project-authored PDF fixture, repeated normalized comparison |
| AC-007 | Unit + license audit | Docling fallback tests and optional-profile inventory |
| AC-008 | CI + manual | pinned workflow; clean Ubuntu 24.04/Python 3.12 run |
| AC-009 | Regression + release | version metadata test and `v0.2.0` tag check |
| AC-010 | Integration + CLI QA | isolated install and hardware-free demo transcript |
| AC-011 | Docs contract + manual | README link/command test and unfamiliar-user walkthrough |
| AC-012 | Contract + visual review | path/branding/claim scans and demo-asset review |
| AC-013 | Manual release audit | clean repository object/ref and GitHub surface inspection |
| AC-014 | Required gates | `/cli-qa`, full verification, `/review`, `/security-review` |

## Test Plan

See [Public Alpha P0 Test Plan](PUBLIC_ALPHA_P0_TEST_PLAN.md).

## Risk Register

See [Public Alpha P0 Risk Register](PUBLIC_ALPHA_P0_RISK_REGISTER.md).

## Validation Commands

- `python3 -m unittest tests.test_docs_sidecar`
- `python3 -m unittest tests.test_diagnostics`
- `python3 -m unittest tests.test_release_version_metadata`
- `python3 -m unittest tests.test_public_release_contract`
- `pytest tests/replay/test_replay_fixtures.py -q --tb=short`
- `./scripts/verify.sh fast`
- `./scripts/verify.sh full`
- `pre-commit run --all-files`

## QA and Security Routing

- Classification: public CLI release, installer, parser behavior, documentation,
  and repository-publication change.
- Risk tier: **High**.
- Required stages: `/cli-qa`, `/review`, `/security-review`,
  `/document-release`, and `/ship`.

## Release / Compatibility Notes

- `--parser pymupdf` is removed and replaced by `--parser pypdf`.
- Base installs no longer include PyMuPDF/PyMuPDF4LLM.
- pypdf is optimized for deterministic text-page extraction; users should use
  the audited optional Docling profile for difficult/scanned/layout-heavy PDFs.
- Existing sidecar schema remains unchanged, but freshness metadata containing
  parser name may require re-ingestion when switching parser.
- `0.2.0` is an alpha-stage `0.x` release, not a stable `1.0` contract.
- The public repositories intentionally do not preserve private development
  history.
