## [Unreleased]

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

### Fixed
- Kept automatic filesystem discovery hard-bounded and deterministic, rejected
  unreadable discovered executables, and contained malformed VS Code file
  encodings without suppressing independent capabilities.
- Removed the orphaned private HIL gitlink and aligned the default installer
  manifest URL with the public repository.
- Aligned README and CLI guidance with the disabled 0.2.0 Docling and semantic
  installer profiles.

## [0.2.0] - 2026-08-13

### Changed
- Prepared the first public alpha release from audited, clean repository snapshots.
- Aligned CLI, package, installer-manifest, changelog, and release-tag version metadata.
- Defined Ubuntu 24.04 LTS x86-64, Python 3.12, and `pipx` as the verified alpha environment; other environments remain unverified.
- Pointed installer release metadata at the public DebugOracle repository while preserving the checkout-local package override.

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
