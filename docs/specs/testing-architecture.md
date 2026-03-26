# DebugOracle Testing Architecture

**Status:** Locked (layer definitions) / Living (assignment of tests to layers)
**Phase:** 1

---

## Purpose

This document defines the testing layers for DebugOracle, what each layer is responsible for, and how they fit together. It is the authoritative source for "which test goes where."

---

## Testing Layers

### Layer 1: Unit Tests

**Scope:** Single function or class, isolated from I/O and external systems.

**Responsibilities:**
- Validate parsing logic (MI parser, RTT parser, SVD parser)
- Validate data transformation functions (register normalization, variable bucketing)
- Validate model construction (builder functions, `from_dict`, `to_dict`)
- Validate rendering logic (report formatting, JSON serialization)

**Boundaries:**
- No file I/O (unless testing serialization, in which case use `tempfile`)
- No subprocess calls
- No network calls
- External systems (debugger, hardware) must be replaced with fixtures or mocks

**Location:** `tests/test_*.py` (any file not in `tests/contracts/` or `tests/hil/`)

**Framework:** `unittest.TestCase`

**Example:** `test_mi_parse.py`, `test_pipeline_renderers.py`, `test_rtt_capture.py`

---

### Layer 2: Contract Tests

**Scope:** Observable system contracts — invariants that must hold regardless of implementation.

**Responsibilities:**
- Validate the five core invariants (determinism, evidence-first, read-only, reproducible, provenance)
- Validate public API shape (exported names, dataclass fields, source descriptors)
- Validate serialization round-trips (save → load produces equal artifact)
- Validate uncertainty handling (missing inputs produce correct `None`/empty behavior)

**Boundaries:**
- May use `tempfile` for file round-trip tests
- Must not depend on live debugger or hardware
- Must not require network access
- Must pass in CI without any external setup

**Location:** `tests/contracts/`

**Framework:** `unittest.TestCase`

**Example:** `tests/contracts/test_core_invariants.py`

**Relationship to unit tests:** Contract tests assert *what* the system does (observable behavior). Unit tests assert *how* specific functions work (implementation detail). A contract test failure means a core invariant was broken. A unit test failure means an implementation detail changed.

---

### Layer 3: Integration Tests

**Scope:** Multiple components working together, with real file I/O, no live hardware.

**Responsibilities:**
- Validate CLI command flows (parse → build → save → render)
- Validate workspace initialization and file layout
- Validate end-to-end artifact production from fixture files

**Boundaries:**
- Real file I/O is expected and encouraged (per AGENTS.md: "File I/O should generally not be mocked")
- Uses fixture files in `tests/fixtures/` (`.mi`, `.rtt`, `.svd`)
- No live debugger, no hardware

**Location:** `tests/test_cli_*.py`, `tests/test_pipeline_*.py`, `tests/test_*_flow.py`

**Framework:** `unittest.TestCase`

**Example:** `test_cli_flow.py`, `test_artifact_schema.py`

---

### Layer 4: Replay Tests (Phase 3 — Deferred)

**Scope:** Replay of real captured debug sessions from saved artifacts.

**Responsibilities:**
- Validate that artifacts captured from real sessions produce stable, expected output
- Detect regressions in rendering and analysis across sessions

**Status:** Deferred to Phase 3. Fixture format must be specified first (see `testing-contracts.md`).

---

### Layer 5: E2E Question Tests (Phase 4 — Deferred)

**Scope:** End-to-end validation of question-answering quality.

**Responsibilities:**
- Validate that a given artifact produces correct answers to specific debug questions
- Covers the `EvidenceAnswer` output path

**Status:** Deferred to Phase 4.

---

### Layer 6: Hardware-in-Loop (HIL) Tests

**Scope:** Tests that require real hardware (MCU, debugger probe).

**Responsibilities:**
- Validate live data acquisition (GDB MI, RTT, register reads)
- Validate full attach/detach flows on real hardware

**Boundaries:**
- Require explicit hardware setup (not run in CI by default)
- Must be marked and skippable via `--ignore=tests/debugoracle-hil-tests`

**Location:** `tests/debugoracle-hil-tests/`

**Framework:** pytest (submodule)

---

## Layer Summary

| Layer | Scope | Location | External I/O | CI Required |
|-------|-------|----------|--------------|-------------|
| 1. Unit | Single function/class | `tests/test_*.py` | None | Yes |
| 2. Contract | Core invariants | `tests/contracts/` | tempfile only | Yes |
| 3. Integration | Multi-component flows | `tests/test_cli_*.py` etc. | File I/O | Yes |
| 4. Replay | Real session replay | `tests/replay/` (Phase 3) | File I/O | Yes |
| 5. E2E Question | Answer quality | `tests/e2e/` (Phase 4) | File I/O | Yes |
| 6. HIL | Live hardware | `tests/debugoracle-hil-tests/` | Hardware | No (explicit) |

---

## Categorizing Existing Tests

The ~25 existing tests in `tests/` fall into layers 1 and 3:

**Contract-like (currently in layer 1, good candidates for layer 2):**
- `test_source_contract.py` — validates source descriptor API shape → move to `contracts/` in Phase 2
- `test_artifact_schema.py` — validates round-trip and schema contracts → move to `contracts/` in Phase 2
- `test_specs_registry.py` — validates public spec registry shape → move to `contracts/` in Phase 2

**Unit (stay in layer 1):**
- `test_mi_parse.py`, `test_rtt_capture.py`, `test_fetch_register_capture.py`
- `test_pipeline_renderers.py`, `test_report_modes.py`, `test_report_snapshot_only.py`
- `test_cortex_debug_*.py`

**Integration (stay in layer 3):**
- `test_cli_flow.py`, `test_cli_live.py`, `test_cli_legacy_cleanup.py`
- `test_installer.py`, `test_docs_sidecar.py`, `test_guard_openocd_launch.py`
- `test_live_backend.py`, `test_run_stop.py`, `test_session_status.py`

---

## Test Discovery

Standard pytest discovery applies:
```bash
pytest tests/ -x -q --tb=short --ignore=tests/debugoracle-hil-tests
```

Contract tests are co-discovered since `tests/contracts/` is within `tests/`. No extra configuration needed.

---

## What Does Not Belong in Tests

- Production fixture files (large captured sessions belong in `tests/fixtures/`, not inline)
- Hard-coded absolute paths
- Tests that require network access without marking
- Tests that assume a specific locale or timezone
