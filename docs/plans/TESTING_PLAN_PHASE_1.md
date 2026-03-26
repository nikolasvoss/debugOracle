# DebugOracle Testing Plan — Engineering Review Results

**Date:** 2026-03-26
**Reviewed Plan:** `docs/plans/testing_rework.md`
**Review Status:** ✅ CLEARED for Phase 1 implementation
**Scope Reduction:** Phases 2-5 deferred; Phase 1 only in this cycle

---

## Executive Summary

The testing rework plan is strategically sound and well-researched. The engineering review **reduced scope to Phase 1 only** (explicit requirements specification) to ship faster and lock in decisions before building phases 2-5.

**Phase 1 Output:** Three specification documents + 5-10 contract tests + EvidenceAnswer dataclass stub.

**Timeline:** ~2-3 weeks to Phase 1 completion.

**Phases 2-5:** Gated by Phase 1 completion; to be scheduled separately.

---

## Review Decisions Locked

### Decision 1: Scope Reduction
- **Original:** 5 phases (requirements → contracts → fixtures → E2E → adversarial)
- **Decision:** Phase 1 only (explicit requirements spec + contract validation)
- **Rationale:** Phase 1 output gates everything else per the plan itself. Ship this first, then use it to guide phases 2-5 incrementally
- **Status:** ✅ Locked

### Decision 2: Phase 1 Deliverable Structure
- **Option chosen:** Split into 3 files
- **Files:**
  1. `docs/specs/testing-requirements.md` — Core invariants, uncertainty handling, safety requirements
  2. `docs/specs/testing-architecture.md` — Testing scope/layers, responsibilities
  3. `docs/specs/testing-contracts.md` — Determinism contract, fixture format spec, metamorphic oracles, adversarial DSL, product ownership
- **Rationale:** Clear separation of concerns; each file focuses on its domain
- **Status:** ✅ Locked

### Decision 3: Phase 1 Implementation Scope
- **Option chosen:** Spec + all implementation (critical missing pieces)
- **Includes:**
  - Three spec documents (prose + examples, not machine-precise)
  - `EvidenceAnswer` dataclass stub (Gap #5 from original plan)
  - 5-10 quick contract tests to validate specs are achievable
- **Rationale:** Phase 1 gates phases 2-5; complete it fully so phases 2-5 run smoothly
- **Status:** ✅ Locked

### Decision 4: Specification Precision Level
- **Option chosen:** Prose + examples (lighter)
- **Approach:**
  - Write requirements in clear English
  - Include concrete examples for ambiguous areas (e.g., "timestamps frozen to empty string")
  - Leave implementation details to be refined during execution
- **Rationale:** Readable specs are more useful than machine-precise specs; implementation will refine details
- **Status:** ✅ Locked

### Decision 5: Spec Validation Approach
- **Option chosen:** Spec + contract tests
- **Includes:**
  - Write 3 spec documents
  - Add 5-10 quick contract tests for core invariants (determinism, evidence-first, read-only)
  - If tests fail: flag gap as "Future: implement X before Phase 2"
- **Rationale:** Validates spec is grounded in current code reality; prevents spec-drift gaps
- **Status:** ✅ Locked

### Decision 6: Specification Maintenance Model
- **Option chosen:** Hybrid (locked core + living details)
- **What's locked:** Core invariants (determinism, evidence-first, read-only, reproducibility, provenance)
- **What's living:** Implementation details (fixture format, DSL operations, metadata structure)
- **Rationale:** Core invariants must be stable; details will evolve as implementation reveals nuances
- **Status:** ✅ Locked

---

## Architecture Review — No Issues Found

### Component: Specification File Structure
- **Status:** ✅ Sound
- **Assessment:** 3-file structure cleanly separates concerns; cross-references manageable
- **Risk:** None identified

### Component: Phase 1 Validation
- **Status:** ✅ Sound
- **Assessment:** Contract tests provide reality-check on spec; prevents implementation surprises
- **Risk:** May uncover gaps, but that's the point — better caught here than in phases 3-5

### Component: EvidenceAnswer Dataclass
- **Status:** ⚠️ Missing, but in Phase 1 scope
- **Assessment:** Gap #5 from original plan. Needs to be added in Phase 1.
- **Implementation:** Simple dataclass stub in `debugoracle/artifacts/models.py`
- **Risk:** None if added early in Phase 1

### Component: Existing Test Infrastructure
- **Status:** ✅ Reusable
- **Assessment:** ~25 existing unittest tests in `tests/`. Can be categorized into contract vs unit during Phase 1
- **Risk:** None

---

## Critical Issues Found

**Count:** 0

No blocking issues identified. Plan is architecturally sound and implementation-ready.

---

## NOT IN SCOPE (Explicit Deferrals)

### Deferred to Phase 2 or later:
1. **Contract test suite** (beyond core invariants) — Full coverage of all contracts deferred
2. **Replay fixtures** (Phase 3) — Real-session fixtures with metadata
3. **E2E question tests** (Phase 4) — Question-centric testing
4. **Adversarial/metamorphic tests** (Phase 5) — Robustness testing
5. **Fixture tooling** — `fixture_reducer.py`, `fixture_validator.py`, `fixture_migrator.py`
6. **Product ownership assignment** — Specs define what ownership looks like; actual assignment deferred

### Rationale:
Phase 1 (specification) must be complete before these phases can proceed. Shipping phases 2-5 without validated specs creates rework risk.

---

## What Already Exists (Reuse Points)

| Component | Current State | Reuse Plan |
|-----------|--------------|-----------|
| Unit tests | ~25 tests using `unittest` framework | Categorize into core invariants (contract) vs implementation details (unit) during Phase 1 |
| Test fixtures | `tests/fixtures/` directory | Format spec in Phase 1 should match existing structure; refine if needed |
| Artifact model | `InvestigationArtifact` in `artifacts/models.py` | Reuse; add `EvidenceAnswer` dataclass alongside |
| Testing framework | `unittest` | Use same framework for Phase 1 contract tests (consistency) |
| Session/config model | `Session` class in `session.py` | Reference in Phase 1 fixture format spec |
| Core invariants | Described in `AGENTS.md` | Translate into testable requirements in `testing-requirements.md` |

**Action:** Phase 1 should audit existing `tests/fixtures/` directory structure and existing artifact model to ensure spec matches current state (or explicitly calls for changes).

---

## Phase 1 Implementation Checklist

### Files to Create:
- [ ] `docs/specs/testing-requirements.md` (5-10 KB)
  - Translate core invariants from AGENTS.md into testable requirements
  - Document uncertainty handling (unknown, insufficient evidence, conflicts)
  - Specify safety requirements (no shell=True, path validation, etc.)
  - Define public behavior change policy

- [ ] `docs/specs/testing-architecture.md` (3-5 KB)
  - Define testing layers: unit, contract, integration, replay, E2E, HIL
  - Specify responsibilities of each layer
  - Explain how they fit together
  - Document which tests belong where

- [ ] `docs/specs/testing-contracts.md` (8-12 KB)
  - **Determinism Contract** — What fields vary? How to compare?
  - **Fixture Format** — Structure, metadata, raw data storage
  - **Fixture Versioning** — `__version__` field, migration strategy
  - **Metamorphic Oracles** — For each transformation (add noise, reorder, etc.), what stays the same?
  - **Adversarial DSL** — Transformer operations (remove_evidence_class, inject_conflict, corrupt_field, etc.)
  - **EvidenceAnswer Type** — Structure, serialization format
  - **Product Ownership** — Who owns each invariant? Escalation path for conflicts?

### Code to Add:
- [ ] `EvidenceAnswer` dataclass in `debugoracle/artifacts/models.py`
  - Simple stub; can be enriched later
  - Should capture: conclusion, confidence, evidence_sources, conflicts, provenance

- [ ] `tests/contracts/` directory (create new directory)
  - Create 5-10 quick contract tests for core invariants:
    1. Deterministic outputs (same input → same output)
    2. Evidence-first behavior (no guessed state in artifacts)
    3. Read-only default (no mutations to target system)
    4. Provenance completeness (every field traceable to source)
    5. Uncertainty handling (unknown on missing evidence)
    6-10. Additional edge case coverage as needed

### Review & Approval:
- [ ] Phase 1 output reviewed and approved before Phase 2 starts
- [ ] Specs locked (core invariants); details marked living where appropriate
- [ ] Contract tests all passing

---

## Key Reference Points

### Gaps from Original Plan (11 Identified)
All 11 gaps are addressed in Phase 1 output structure:

1. **Fixture Format** → `testing-contracts.md`
2. **Determinism Contract** → `testing-contracts.md`
3. **Metamorphic Oracle Definition** → `testing-contracts.md`
4. **Adversarial Transformation DSL** → `testing-contracts.md`
5. **EvidenceAnswer Type** → `testing-contracts.md` + code implementation
6. **Fixture Versioning** → `testing-contracts.md`
7. **Fixture Maintenance Labor** → `testing-contracts.md`
8. **Contract Tests vs Invariants** → `testing-architecture.md` + `testing-contracts.md`
9. **Fixture Feedback Loop** → `testing-contracts.md`
10. **Product Ownership** → `testing-contracts.md`
11. **Determinism Fuzzer False Positives** → `testing-contracts.md`

### Core Invariants (From AGENTS.md)
Phase 1 requirements must protect:
1. **Deterministic** — Same inputs → same outputs, no hidden state
2. **Evidence-first** — No inferred or guessed state in artifacts
3. **Read-only by default** — No mutation of target systems
4. **Reproducible** — Artifacts allow offline reconstruction of reasoning
5. **Explicit provenance** — Every piece of data traceable to origin

---

## Next Steps

1. **Create Phase 1 spec files** using the structure above
2. **Add EvidenceAnswer dataclass** stub
3. **Write 5-10 contract tests** to validate specs
4. **Lock specs** via code review
5. **Schedule Phase 2** (contract test suite expansion) after Phase 1 approval

---

## Review Report

| Section | Result | Notes |
|---------|--------|-------|
| Step 0: Scope Challenge | ✅ RESOLVED | Phase 1 only; phases 2-5 deferred |
| Architecture Review | ✅ CLEAR | No issues; 3-file structure sound |
| Code Quality Review | ✅ CLEAR | Prose + examples approach is readable |
| Test Review | ✅ CLEAR | Contract tests validate specs |
| Performance Review | ✅ CLEAR | Hybrid version model (locked core, living details) |
| NOT in scope | ✅ DOCUMENTED | Phases 2-5 explicitly deferred |
| What already exists | ✅ MAPPED | Reuse points identified |
| Implementation checklist | ✅ PROVIDED | Clear tasks for Phase 1 |

**VERDICT:** ✅ ENG REVIEW CLEARED — Phase 1 is ready to implement.

---

**Document created:** 2026-03-26
**Review conducted by:** Claude Code /plan-eng-review
**Status:** Phase 1 implementation can begin immediately
