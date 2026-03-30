# DebugOracle Testing Requirements

**Status:** Locked (core invariants) / Living (implementation details)
**Phase:** 1

---

## Purpose

This document translates DebugOracle's core invariants into testable requirements. It defines what must be true of the system's observable behavior, not how tests are implemented.

---

## Core Invariants (Locked)

These five invariants are the foundation of the system. No change may break them. Tests that validate these invariants are **contract tests** and must remain in the test suite.

### 1. Deterministic

**Requirement:** Given the same raw inputs (GDB MI log, RTT log, SVD file, session config), the system must produce byte-for-byte identical artifacts and reports.

**Testable definition:**
- `REQ-DET-001`: Calling `build_bundle_from_text(mi_text, rtt_text)` twice with identical inputs produces equal artifacts (field-by-field comparison).
- `REQ-DET-002`: Fields that naturally vary (e.g., `captured_at` timestamps) must be explicitly frozen or omitted from determinism assertions.
- `REQ-DET-003`: Frozen timestamp convention: `captured_at` is set by the caller; tests pass a fixed value (e.g., `""`).
- `REQ-DET-004`: No random values, UUIDs generated at artifact creation time, or system clock reads inside the build pipeline.

**What is NOT a violation:**
- Differences in `captured_at` when the caller passes different values.
- Differences across schema versions (different inputs).

---

### 2. Evidence-First

**Requirement:** Artifacts must not contain inferred or guessed state. Every field must trace back to a source.

**Testable definition:**
- `REQ-EVD-001`: An artifact built from empty inputs (no MI, no RTT) must not contain synthetic values for `stop_reason`, `pc`, `lr`, `sp`, or variable entries. These fields must be `None` or empty.
- `REQ-EVD-002`: `VariableEntry.origin` must not be empty for any entry present in an artifact. Each entry must name its source.
- `REQ-EVD-003`: `InvestigationArtifact.provenance` must be non-empty when sources are present.

**What is NOT a violation:**
- Default empty collections (`frames: []`, `sources.rtt.lines: []`) when no data is available.
- Schema defaults for optional fields (`schema_version`, `parse_warnings`).

---

### 3. Read-Only by Default

**Requirement:** No operation in the build pipeline may mutate the target system (debugger, hardware, file system outside the workspace).

**Testable definition:**
- `REQ-RO-001`: The artifact build pipeline (`build_bundle_from_text`, `build_bundle`) must not call `subprocess.run`, `os.system`, or any shell-invoking API (verified by import analysis or mock injection).
- `REQ-RO-002`: `shell=True` must never appear in the build pipeline.
- `REQ-RO-003`: File writes must be limited to the `.dbgoracle/` workspace directory.
- `REQ-RO-004`: The render path must not mutate an artifact in-place.

**What is NOT a violation:**
- CLI commands that explicitly read from a live debugger (these are out of build-pipeline scope and covered by integration tests).
- The docs sidecar feature (`ingest_documents`, `search_documents`): sidecar directories are intentionally written adjacent to the source document (e.g., `manual.pdf.dbgoracle-docs/`) so they travel with the document. This is an explicit carve-out from REQ-RO-003's workspace-boundary constraint.

---

### 4. Reproducible

**Requirement:** An artifact must contain sufficient information to reconstruct the reasoning offline, without access to the live debug session.

**Testable definition:**
- `REQ-REPR-001`: An artifact with `sources.gdb.embedded = True` must contain the full `raw_text` of the GDB MI log.
- `REQ-REPR-002`: An artifact with `sources.rtt.embedded = True` must contain the full `raw_text` of the RTT log.
- `REQ-REPR-003`: Core artifact fields must survive a save → load round-trip unchanged. (Known exception: `sources.gdb.events[].payload` nested values are stringified on load — tracked as a serialisation limitation.)

---

### 5. Explicit Provenance

**Requirement:** Every piece of data in an artifact must be traceable to its origin.

**Testable definition:**
- `REQ-PROV-001`: `VariableEntry.origin` must be set to a non-empty string for all entries.
- `REQ-PROV-002`: `ArtifactSources` must correctly report `embedded = True/False` based on whether raw source data is present.
- `REQ-PROV-003`: `InvestigationArtifact.provenance` must name the sources used when sources are embedded.

---

## Uncertainty Handling Requirements

When evidence is missing, incomplete, or contradictory, the system must be explicit rather than silent.

### Missing Evidence
- `REQ-UNC-001`: Fields with no backing evidence must be `None` (not `""`, not `"unknown"`, not synthesized).
- `REQ-UNC-002`: Example: `stop_reason = None` when no MI stop event is present.

### Insufficient Evidence
- `REQ-UNC-003`: `parse_warnings` must be populated when the parser encounters data it cannot fully interpret.
- `REQ-UNC-004`: Partially parsed data must include what was parsed; the warnings list must explain what failed.

### Conflicting Evidence
- `REQ-UNC-005`: When two sources provide conflicting values for the same field, the system must either:
  a. Pick the authoritative source (documented in the relevant spec), or
  b. Emit a parse warning describing the conflict.
- `REQ-UNC-006`: Silent discarding of conflicting data is not allowed.

---

## Safety Requirements

These requirements prevent security issues and unsafe system interactions.

### Subprocess Safety
- `REQ-SAFE-001`: `shell=True` is **prohibited** in all production code paths.
- `REQ-SAFE-002`: Path arguments to subprocess calls must be validated (absolute or workspace-relative).
- `REQ-SAFE-003`: Violation: immediate failing test.

### Path Validation
- `REQ-SAFE-004`: All file reads and writes must validate the path is within expected boundaries.
- `REQ-SAFE-005`: Paths constructed from external input (e.g., snapshot IDs, user config) must be sanitized.

### File Access Control
- `REQ-SAFE-006`: Build pipeline reads: only workspace files and fixture files.
- `REQ-SAFE-007`: Build pipeline writes: only workspace (`.dbgoracle/`) directory.

---

## Public Behavior Change Policy

Any change to these behaviors requires:
1. A spec update (this document or `testing-contracts.md`).
2. A contract test update or addition.
3. Explicit approval before merging.

**Covered behaviors:**
- Artifact field names and types (`InvestigationArtifact`, `EvidenceAnswer`)
- Serialization format (JSON keys, schema version)
- CLI output format (rendered reports)
- Provenance conventions (`VariableEntry.origin` format)
