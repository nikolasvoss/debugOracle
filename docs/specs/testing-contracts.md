# DebugOracle Testing Contracts

**Status:** Locked (contract definitions) / Living (implementation details, DSL operations, fixture format details)
**Phase:** 1

---

## Purpose

This document specifies the contracts that tests must enforce. It answers: what exactly is being tested, how comparisons are made, and what the fixture format looks like.

---

## Determinism Contract

### What "deterministic" means in practice

Two calls to `build_bundle_from_text(mi_text, rtt_text)` with identical inputs must produce equal artifacts. "Equal" means field-by-field equality of the `InvestigationArtifact` dataclass.

### Fields that are expected to vary

| Field | Varies because | How to handle in tests |
|-------|---------------|----------------------|
| `captured_at` | Caller-provided timestamp | Freeze: pass `""` or a fixed value |
| `snapshot_id` | UUID or hash generated at call time | Freeze: patch the ID generator or accept any non-empty string |

All other fields must be deterministic given the same inputs.

### Comparison method

Use `dataclasses.asdict(artifact)` → compare resulting dicts after stripping variable fields. Do not compare `captured_at` or `snapshot_id` for equality; assert they are strings.

### False positive prevention

Determinism tests must not compare timestamps embedded in raw RTT or MI text (those are source data, not artifact fields). If source text contains timestamps, the test must use synthetic source text with frozen values.

---

## Fixture Format Specification

### Purpose

Fixtures are static files used to run tests without live hardware. They represent raw captured data (MI log, RTT log, SVD file) or serialized artifacts (JSON).

### File types

| Extension | Content | Location |
|-----------|---------|----------|
| `.mi` | Raw GDB MI log text | `tests/fixtures/` |
| `.rtt` | Raw RTT log text | `tests/fixtures/` |
| `.svd` | SVD peripheral register definition | `tests/fixtures/` |
| `.json` | Serialized `InvestigationArtifact` | `tests/fixtures/` |

### Fixture metadata

Fixtures do not require a metadata header in Phase 1. In Phase 3 (replay fixtures), each fixture bundle will include a `__version__` field and provenance metadata. For now, raw text files have no structured metadata.

### Fixture versioning (`__version__` — Living)

JSON artifact fixtures carry a `schema_version` field (currently `"4"`). Tests that load fixture JSON must:
1. Check `schema_version` matches `CURRENT_BUNDLE_SCHEMA_VERSION`, or
2. Explicitly document that they are testing strict-load failure behavior for unsupported schemas.

When `CURRENT_BUNDLE_SCHEMA_VERSION` is bumped, existing JSON fixtures must be either migrated or moved to a `tests/fixtures/legacy/` directory.

### Migration strategy (Living)

Phase 3 will define `fixture_migrator.py`. Until then: if a fixture is stale, update it manually and record the reason in a comment or test docstring.

---

## EvidenceAnswer Type

### Purpose

`EvidenceAnswer` represents the system's structured response to a debug question. It is a higher-level output than `InvestigationArtifact` — it synthesizes evidence into a conclusion.

### Structure

```python
@dataclass(frozen=True)
class EvidenceAnswer:
    question: str
    conclusion: str
    confidence: str          # "high" | "medium" | "low" | "unknown"
    evidence_sources: list[str]
    conflicts: list[str]
    provenance: dict[str, str]
```

### Field definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | `str` | Yes | The question being answered |
| `conclusion` | `str` | Yes | The answer. May be `"unknown"` if evidence is insufficient |
| `confidence` | `str` | Yes | Confidence level: `"high"`, `"medium"`, `"low"`, or `"unknown"` |
| `evidence_sources` | `list[str]` | Yes | Source IDs that contributed to this answer |
| `conflicts` | `list[str]` | Yes | Human-readable descriptions of any conflicting evidence |
| `provenance` | `dict[str, str]` | Yes | Maps field names to the source that provided the value |

### Uncertainty convention

When evidence is insufficient to answer:
- `conclusion = "unknown"`
- `confidence = "unknown"`
- `evidence_sources = []` (or partial list of what was checked)
- `conflicts = []` (or list of what conflicted, if applicable)

This is the canonical "I don't know" response. It is preferable to a guess.

### Serialization format (Living)

`EvidenceAnswer` is a frozen dataclass. Serialization via `dataclasses.asdict()` produces a flat JSON dict. No custom serializer required in Phase 1.

---

## Metamorphic Oracles

A metamorphic oracle defines: "if I apply transformation T to the input, property P must still hold."

These oracles are used in Phase 5 adversarial tests. They are specified here so contract tests can validate the properties they depend on.

### Oracle 1: Add Noise

**Transformation:** Append unrecognized lines to the end of the MI log.
**Property that must hold:** `stop_reason`, `pc`, `lr`, `sp`, `frames` are unchanged. `parse_warnings` may increase.

### Oracle 2: Reorder RTT Lines

**Transformation:** Shuffle the order of RTT lines.
**Property that must hold:** `sources.rtt.lines` contains the same set of lines (order may differ). All other fields are unchanged.

### Oracle 3: Remove Evidence Class

**Transformation:** Remove all lines of a specific evidence type (e.g., all `*stopped` events from MI).
**Property that must hold:** The removed evidence type's corresponding fields become `None` or empty. Other fields are unchanged.

### Oracle 4: Inject Conflict

**Transformation:** Duplicate a stop event with a different stop reason.
**Property that must hold:** `parse_warnings` contains a conflict description. `stop_reason` is set to one of the two values (documented choice). No silent discard.

### Oracle 5: Corrupt Field

**Transformation:** Replace a valid hex address (`pc`) with a non-hex string.
**Property that must hold:** `pc` is `None` or the raw string is preserved. `parse_warnings` notes the invalid value.

---

## Adversarial Transformation DSL (Living)

Phase 5 will implement a DSL for programmatically constructing adversarial inputs. The operations are defined here so Phase 1 contract tests can test the properties those operations depend on.

### Operations (conceptual, not yet implemented)

| Operation | Description |
|-----------|-------------|
| `remove_evidence_class(source, kind)` | Remove all events of a given kind from a source |
| `inject_conflict(field, value)` | Add a duplicate event with a conflicting value |
| `corrupt_field(field, bad_value)` | Replace a field value with an invalid value |
| `add_noise(lines)` | Append unrecognized lines to an input |
| `reorder(source)` | Shuffle events in a source |
| `truncate(source, n)` | Keep only the first N lines of a source |

### Phase 1 scope

Contract tests do not use this DSL. They use handcrafted fixture strings to test the same properties. The DSL is specified here to ensure Phase 1 properties are compatible with Phase 5 automation.

---

## Product Ownership

### Ownership model

Each core invariant has an owner — the person or role responsible for:
- Deciding whether a change to that invariant is acceptable
- Reviewing contract tests that protect the invariant
- Resolving conflicts when two requirements clash

### Escalation path

1. If a PR breaks a contract test: the PR author must justify the break or fix it.
2. If the break is intentional (invariant is being changed): requires spec update + reviewer sign-off.
3. If two invariants conflict: escalate to project owner; document the resolution in this file.

### Assignment

| Invariant | Owner | Responsibilities |
|-----------|-------|-----------------|
| Deterministic | project maintainer | Approve changes to artifact generation, serialization, caching |
| Evidence-first | project maintainer | Reject inferred or guessed state in output rendering or conclusion logic |
| Read-only by default | project maintainer | Approve commands that interact with targets or modify input files |
| Reproducible | project maintainer | Approve changes to save/load round-trip and raw source embedding |
| Explicit provenance | project maintainer | Reject code that loses source linkage in evidence traversal or rendering |

---

## Fixture Feedback Loop (Living)

When a contract test fails due to a fixture being stale:

1. Determine whether the fixture is wrong or the behavior changed.
2. If behavior changed intentionally: update the fixture and the relevant spec section.
3. If behavior changed unintentionally: treat as a regression — fix the code, not the fixture.
4. Record the reason for any fixture update in the commit message.

Phase 3 will introduce `fixture_validator.py` to automate stale-fixture detection.

---

## Determinism Fuzzer False Positives (Living)

If a future determinism fuzzer reports a false positive (two runs differ but for a legitimate reason):

1. The variable field must be documented in the "Fields that are expected to vary" table above.
2. The fuzzer must be updated to exclude that field.
3. Do not suppress the entire test — add a field-specific exclusion.

Currently known variable fields: `captured_at`, `snapshot_id`.

---

## Fixture Curation Process (Living)

Fixtures are the raw captured sessions used by replay, adversarial, and metamorphic tests
(Phases 3–5). This section defines the process for creating and maintaining them.

### Turning a bug into a fixture

When a real bug is found, capture it as a fixture so it becomes a permanent regression test.

1. **Capture** (~15 min): Reproduce the bug, capture the DebugOracle session (GDB MI log, RTT log, registers, etc.).
2. **Minimize** (~30–45 min): Remove noise and irrelevant data to produce the smallest input that still reproduces the issue. Use `tests/helpers/fixture_reducer.py` (Phase 3) for automated trimming, then review manually.
3. **Validate** (~15 min): Run DebugOracle on the minimized fixture multiple times. Confirm it reproduces consistently and deterministically.
4. **Document** (~15 min): Write metadata (`metadata.yaml`) with questions, expected conclusions, required evidence, and forbidden behaviors.
5. **Review** (~15 min): Code-review the fixture before merge. Verify it is accurate and will be useful long-term.

**Total per fixture: ~1.5–2 hours.**

### Quality gates for a fixture

A fixture is ready to merge when:
- It reproduces the bug deterministically on at least two runs.
- It is minimized to the smallest input that still demonstrates the behavior.
- Its `metadata.yaml` names the engineering question, expected conclusion, and required evidence.
- It passes the fixture validator (Phase 3: `tests/helpers/fixture_validator.py`).

### Schema migration

When `InvestigationArtifact` schema changes (new fields, renamed fields):
1. Update `__version__` (or `schema_version`) in the fixture.
2. Run `tests/helpers/fixture_migrator.py` (Phase 3) to update all fixtures atomically.
3. Run the full suite to confirm fixtures still produce expected results.

**Cost per schema change: ~30 min with migration tooling.**

### Corpus growth targets

| Phase | Fixtures | Est. labor |
|-------|----------|------------|
| Phase 3 initial | 3–5 | ~5–10 hours |
| Per quarter (from bugs) | 1–2 | ~2–4 hours |
| Year 1 target | ~10–15 | — |
