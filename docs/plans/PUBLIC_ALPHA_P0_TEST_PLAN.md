# Public Alpha P0 Test Plan

**Status:** Closed — private `v0.2.0` release evidence retained; release withdrawn before public availability

## Execution Summary

This test plan is retained as historical private release evidence. The implemented
contracts were exercised by the focused parser, diagnostics, metadata,
public-release, automatic-initialization, and reference-workspace tests. CLI QA
passed its 14-case matrix, the final pypdf 6.16.1 revalidation passed 105 focused
tests, and `./scripts/verify.sh full` passed Ruff, formatting, Pyright, the
non-HIL test suite, coverage, and Bandit.

The hardware-free demo was reproduced from the project-owned snapshot and
two-page PDF, including deterministic report rendering and BM25 documentation
search. The video/animation review was not run because that optional asset was
deferred. The replacement clean-history candidate-clone procedure was not run
as written because the owner approved publication from the existing reviewed
repositories. These deviations are recorded in the task spec and implementation
plan rather than reported as passing tests.

## Purpose

Prove that the audited `0.2.0` public alpha is license-conscious, free of known
private release artifacts, reproducible from a clean clone, deterministic on its
hardware-free demo, and honest about its supported environment.

## Automated Contract Tests

### Release surface

Add `tests/test_public_release_contract.py` to assert:

- `LICENSE`, `SECURITY.md`, and `THIRD_PARTY_NOTICES.md` exist.
- Package metadata identifies Apache-2.0, the README, and public project URLs.
- No tracked `*.pdf.dbgoracle-docs/`, `*.dbgoracle-docs/`, `embeddings.npy`, or
  prohibited vendor PDF exists.
- No `pymupdf`, `pymupdf4llm`, `import fitz`, or `import pymupdf` remains in the
  base dependency/runtime surfaces.
- Public submodule URLs are HTTPS, public, and pinned; HIL is not required.
- Public docs and fixtures contain no `/home/niko/`, stale DebugAssist branding,
  “No Hallucination” guarantee, or controlled-write roadmap promise.
- Required README links and demo inputs resolve inside the public tree.

Extend `tests/test_release_version_metadata.py` to assert:

- Canonical version is `0.2.0`.
- CLI, dynamic package metadata, manifest, and newest released changelog heading
  agree.
- Release URLs use the public repository name.
- Release validation rejects a tag other than `v0.2.0` when a tag is supplied by
  CI.

### pypdf parser

Extend `tests/test_docs_sidecar.py` using a small project-authored PDF fixture:

- Extract text from two or more pages in source order.
- Preserve one-based page provenance in chunks and envelope metadata.
- Produce identical normalized results in two runs.
- Classify empty and image-only pages explicitly.
- Fail clearly on malformed or encrypted input.
- Preserve Unicode and technical identifiers needed for search.
- Keep the existing sidecar schema and atomic publish behavior.
- Mark freshness against parser `pypdf`, not `pymupdf`.
- Route degraded Docling mapping to pypdf with explicit warning/provenance.
- Preserve Docling output when fallback fails; do not replace it with fabricated
  pypdf output.

Update diagnostics tests to verify pypdf readiness/remediation and the absence
of PyMuPDF installation advice.

## Integration Tests

### Clean reference clone

1. Clone the candidate reference repository anonymously into a temporary
   directory.
2. Initialize the pinned Pico SDK submodule if the selected example needs it.
3. Confirm no private authentication, vendor PDF, sidecar, build output, or HIL
   repository is required.
4. Validate all documentation links and the generated-firmware provenance file.

### Clean main clone and installation

On Ubuntu 24.04 x86-64 with Python 3.12 and `pipx`:

1. Clone the candidate main repository anonymously with required submodules.
2. Run `./scripts/install/linux.sh --docs-tools none` in an isolated user/VM.
3. Assert successful exit and `dbgoracle --version == 0.2.0`.
4. Confirm the environment contains pypdf and does not contain
   PyMuPDF/PyMuPDF4LLM as DebugOracle dependencies.
5. Exercise uninstall and confirm documented cleanup boundaries.

### Hardware-free demo

1. Copy the sanitized evidence fixture into a temporary workspace.
2. Run the documented `fetch` inputs and write the snapshot to the temporary
   workspace.
3. Run `report` against that snapshot.
4. Assert the documented stop/evidence observation, provenance, gap, and next
   debugging direction.
5. Repeat from a new temporary workspace and compare normalized results.
6. Assert no hardware, socket, OpenOCD process, or network access occurs.

## Failure-Path Tests

- Missing `pipx` produces the existing structured install block.
- Unsupported platform is reported without guessed installation actions.
- Private, missing, or unresolvable required submodule blocks release validation.
- Version or tag mismatch blocks release validation.
- Vendor PDF or sidecar reintroduction blocks the public contract.
- Malformed/encrypted/scanned PDF returns explicit failed/partial quality.
- Docling failure followed by pypdf failure reports both facts without hiding the
  original evidence.
- Missing optional Docling/model dependencies do not break base installation or
  the hardware-free demo.
- A fixture with a maintainer-home path fails the public contract.

## Manual Validation

- Verify the exact STM32Cube package license and origin for every retained
  generated tree.
- Verify every optional dependency and model license recorded in the notice
  inventory.
- Review video/animation and transcript for matching commands and outputs.
- Complete the README as an unfamiliar user on the declared platform.
- Inspect candidate Git object/ref lists to confirm they contain only the clean
  public history.
- Confirm private archives, their Actions logs, issues, pull requests, and
  branches remain private and unlinked from the public repositories.
- Enable and test GitHub private vulnerability reporting after public repository
  creation and before announcement.

## Validation Commands

```bash
python3 -m unittest tests.test_docs_sidecar
python3 -m unittest tests.test_diagnostics
python3 -m unittest tests.test_release_version_metadata
python3 -m unittest tests.test_public_release_contract
pytest tests/replay/test_replay_fixtures.py -q --tb=short
./scripts/verify.sh fast
./scripts/verify.sh full
pre-commit run --all-files
```

## Exit Criteria

- Every acceptance criterion has recorded passing evidence.
- `/cli-qa`, `/review`, and `/security-review` have no unresolved release
  blockers.
- Both clean candidates pass anonymous clone validation.
- The final demo transcript matches the reviewed `v0.2.0` candidate exactly.
