## [Unreleased]

### Added
- Added native checkout install and uninstall launchers for current macOS and
  Windows PowerShell, backed by the existing verified pipx installer core.

### Changed
- Expanded installer contract CI to Linux, Apple Silicon macOS, Intel macOS,
  and Windows, and added a release-time dependency vulnerability audit.

### Fixed
- Made managed PATH updates atomic and hardened Windows PATH ownership and
  concurrent-update recovery so uninstall never removes an unproven entry.

## [0.3.1] - 2026-08-26

### Changed
- Narrowed supported Python runtimes to Python 3.12.x on Linux, current macOS,
  and current Windows PowerShell; retained installer contract coverage for all
  supported platforms and removed the broad Python compatibility matrix.

## [0.3.0] - 2026-08-24

### Changed
- Reworked onboarding around an agent-first README, with plain-language
  capabilities, requirements, a hardware-free demo, and linked setup guides.
- Fresh workspace setup now creates optional `debugoracle-input/` and managed
  ignore rules. Automatic discovery prioritizes that folder, then uses bounded
  common workspace locations without guessing among ambiguous inputs.
- Agent-authorized workspace documentation ingestion now stores new search data
  under `.dbgoracle/documentation-search/`; document search and status retain
  compatibility with legacy sibling sidecars.
- Archived the public-alpha P0 planning set with the actual release outcome,
  accepted deviations, and residual risks.
- Clarified the contribution policy for third-party runtime dependencies.
- Added isolated-artifact release gates across the supported Python
  compatibility matrix. Pull-request and `main` CI temporarily exclude the
  private reference workspace; tagged release validation still requires its
  complete recursive checkout.
- Centralized PEP 440 handling and cryptographically bound remote installer
  artifacts to a restricted manifest.
- Recorded exact provenance, license evidence, and hashes for retained STM32,
  SVD, Pico SDK, and nested submodule material.
- Aligned release, installer, security, package, and onboarding URLs with the
  canonical `nikolasvoss/debugOracle` repository after its GitHub rename.

### Fixed
- Restored the declared Python 3.10 CI compatibility for installer imports and
  release-contract tests, and made workspace initialization tests independent
  of host OpenOCD availability.
- Kept artifact verification reproducible by pinning its Twine version to the
  retained `packaging==26.0` dependency contract.
- Hardened workspace-derived paths against symlink traversal and made
  canonical state publication atomic.
- Made malformed GDB/MI input fail deterministically instead of risking a
  parser stall.
- Bound detached `stop` operations to the recorded Linux process instance and
  exact workspace/argument identity.
- Corrected `fetch` resolution exit codes, partial-evidence warning streams,
  and TCP port validation.
- Kept repeated artifact builds deterministic outside the documented
  `captured_at` and `snapshot_id` fields.
- Removed unsupported Docling and semantic installation commands from
  `docs doctor` while their license gate remains open.
- Pinned the audited base PDF parser to `pypdf` 6.16.1.

## [0.2.0] - 2026-08-21

### Added
- Added opt-in `init-workspace --auto` planning and application with stable text
  and versioned JSON capability results for documentation, debug scaffold, and
  register-catalog setup.
- Added `--yes` authorization for automatic ingestion of locally discovered
  PDFs under `doc/` and `docs/`, including `docs/vendor/`.

### Changed
- Automatic workspace initialization now completes each unambiguous local
  capability independently, preserving useful docs-only or SVD-only progress
  when executable or OpenOCD inputs are absent.
- Automatic discovery now reports candidate provenance, ambiguities, and exact
  next actions without building firmware, downloading resources, contacting a
  probe, or modifying source documents.
- Documented a hardware-free evidence-synthesis showcase that connects recorded
  RTT, firmware source, RCC/USART register values, and a project-owned register
  reference.
- The fast verification preflight now runs the non-HIL test suite without
  coverage, while the required full gate runs the same suite once with the
  existing coverage threshold and has a three-minute CI timeout.
- Prepared the first public alpha release from audited repository snapshots.
- Aligned CLI, package, installer-manifest, changelog, and release-tag version
  metadata.
- Defined Ubuntu 24.04 LTS x86-64, Python 3.12, and `pipx` as the verified alpha
  environment; other environments remain unverified.
- Pointed installer release metadata at the public DebugOracle repository while
  preserving the checkout-local package override.

### Fixed
- Kept automatic filesystem discovery hard-bounded and deterministic, rejected
  unreadable discovered executables, and contained malformed VS Code file
  encodings without suppressing independent capabilities.
- Removed the orphaned private HIL gitlink and aligned the default installer
  manifest URL with the public repository.
- Aligned README and CLI guidance with the disabled 0.2.0 Docling and semantic
  installer profiles.

## [0.1.2] - 2026-04-08

### Added
- Replay fixture regression suite under `tests/replay/` with scenario-based fixture bundles:
  `signal_received_stop`, `missing_stop_evidence`, and `conflicting_stop_events`.
- Shared test helpers in `tests/helpers/` for fixture loading and deterministic artifact comparison.
- Replay fixture track completed; durable requirements and contracts live in
  `docs/specs/testing-*.md`.

### Changed
- Replay tests now auto-discover fixture bundles from `tests/fixtures/` instead of relying on a hardcoded fixture list.
- Artifact comparison helper now supports opt-in exclusion of `sources.gdb.events` for save/load round-trip parity checks while keeping determinism checks strict by default.
- Pre-commit `bandit` hook now runs via `.venv/bin/bandit` for consistent local execution.

### Fixed
- Fixture metadata loading now supports YAML parsing (with JSON fallback) instead of strict JSON-only parsing.
- Full validation gate now runs cleanly with `./.venv/bin/pre-commit run --all-files`.

## [0.1.1] - 2026-04-05

### Added
- Automatic docs search mode reporting (`mode=bm25|hybrid`) in text and JSON output.
- Regression coverage for Docling page-mapping fallback edge cases and semantic model caching.

### Changed
- `dbgoracle docs search` now auto-selects hybrid ranking when semantic embeddings are present.
- Removed `--semantic` from `docs search`; semantic availability is inferred from sidecar embeddings.
- Semantic model loading now uses lazy in-process caching to avoid repeated initialization.
- Documentation updated to reflect auto-mode search behavior.

### Fixed
- Semantic runtime failures now degrade cleanly to BM25 search with explicit warnings.
- Docling ingest now retries with PyMuPDF when page mapping is untrusted on multi-page PDFs.
- Untrusted page mapping is preserved as `partial` even when fallback also collapses page spans.
