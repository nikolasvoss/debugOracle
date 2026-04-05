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
