# DebugOracle — Testing Quality Implementation Plan

## Goal

Strengthen DebugOracle’s automated test quality so that it validates not only code correctness, but also the **product’s core promise**:

> DebugOracle must act as a deterministic, evidence-first, reproducible, read-only debugging evidence system that remains trustworthy in agentic coding workflows.

This plan focuses first on the highest-value improvements:

1. define explicit test requirements
2. encode core invariants as contract tests
3. build replayable fixtures from real sessions
4. add question-centric end-to-end tests
5. add adversarial and metamorphic tests before scaling breadth

The aim is not simply “more tests.”  
The aim is a test system that protects the actual product model and prevents drift toward hidden inference, nondeterminism, and ungrounded outputs.

---

# 1. Why this plan exists

## Problem

Current unit tests are useful, but they are not enough by themselves.

Unit tests usually protect:
- small functions
- parser behavior
- edge-case handling
- implementation correctness at a local level

But DebugOracle is not just a library. It is a **debug evidence pipeline** for humans and AI agents. That means the highest-risk failures are often not simple function-level bugs.

The most dangerous failures are things like:
- a conclusion is rendered without enough evidence
- provenance is dropped during transformation
- the same session produces different artifacts on different runs
- missing evidence leads to implied certainty instead of `unknown`
- irrelevant noise changes the conclusion
- the system behaves “helpfully” instead of truthfully
- CLI/report behavior drifts away from the product model in `AGENTS.md`

These failures can survive a strong unit test suite.

## Strategic testing shift

Testing should move from:

- “does this function work?”

toward:

- “does the system preserve its invariants?”
- “does the product answer questions only from evidence?”
- “does it degrade safely under missing/noisy/conflicting data?”
- “does it remain deterministic and reproducible under realistic workflows?”

This plan implements that shift gradually.

---

# 2. Product-level test philosophy

The test system should enforce these principles:

## 2.1 Test the promises, not only the code

The strongest source of requirements is not the current implementation.  
It is the intended product model described in `AGENTS.md` and in specs.

That means tests should directly protect:
- determinism
- evidence-first behavior
- read-only boundaries
- reproducibility
- provenance completeness
- path/security safety
- uncertainty handling
- separation of parsing / logic / rendering concerns

## 2.2 Prefer requirement-backed tests over incidental tests

A weak test says:
- “this helper returns 7”

A strong test says:
- “if required evidence is absent, the public result must remain unknown and must not overclaim”

The second kind of test survives refactors better and better protects product quality.

## 2.3 Test the full reasoning surface

DebugOracle’s value is not only parsing logs. It is producing evidence artifacts that can answer engineering questions.

Therefore, a strong suite needs multiple layers:
- unit tests for local correctness
- contract tests for invariants
- replay tests for real-session regression protection
- question-centric e2e tests for agent usefulness
- adversarial/metamorphic tests for trustworthiness

## 2.4 Reward honest incompleteness

A key product requirement should be:

> When the evidence is insufficient, the system must say so clearly.

This is especially important in agentic coding environments, where “plausible sounding” failure modes are dangerous.

Tests must explicitly reward:
- `unknown`
- `insufficient evidence`
- unresolved conflict reporting
- narrow claims instead of broad claims

---

# 2.5 Critical Specification Gaps (Identified in Review)

Before implementing, this plan must resolve 11 specification gaps. These are not blockers but must be settled in Phase 1 output.

## Gap #1: Fixture Format & Structure

**The problem:** Plan uses "frozen Python dataclasses" but the artifact format is ambiguous.

**Decision required (Phase 1 output):**
- Are fixtures Python code (`.py` files, imported) or data files (JSON/YAML)?
- How is metadata stored (separate `.meta.py` file, inline in dataclass, YAML)?
- What's the canonical format for large data (GDB MI logs, register dumps)?

**Recommendation:** Fixtures are frozen Python dataclasses in `tests/fixtures/{name}/fixture.py`, with optional `metadata.py` for test metadata. Raw data (logs, dumps) stored as `.json` or `.log` files alongside, loaded at test time.

## Gap #2: Determinism Contract Definition

**The problem:** "Byte-identical output" is too strict and too vague simultaneously.

**Decision required (Phase 1 output):**
- Which fields are allowed to vary? (timestamps? session IDs? list order?)
- What counts as "determinism"? (byte-identical JSON? canonical serialization? semantic equivalence?)
- How do you handle fields like `timestamp: str = ""`? Are they frozen in tests or dynamic?

**Recommendation:** Specification must document "allowed variance": timestamps are frozen in fixtures to `""` (empty string), list iteration uses `sorted()`, all other fields are byte-identical. Determinism fuzzer validates via canonical JSON comparison.

## Gap #3: Metamorphic Oracle Definition

**The problem:** "Add noise, reorder logs, duplicate evidence" — but what should stay the same?

**Decision required (Phase 1 output):**
- For each metamorphic transformation, define the expected relationship:
  - `add_irrelevant_noise`: conclusion state stays the same, confidence may lower
  - `reorder_non_semantic_records`: output is semantically identical after canonicalization
  - `duplicate_evidence_lines`: conclusion stays identical
  - `remove_non_essential_evidence`: conclusion stays identical if removed source wasn't required
  - `remove_essential_evidence`: conclusion degrades to `unknown`, not a false positive

**Recommendation:** Each metamorphic test carries a `.oracle` field that specifies which assertion strategy to use (strict equality, state-only, semantic equivalence).

## Gap #4: Adversarial Transformation DSL

**The problem:** "Generic transformers + family overrides" is too abstract.

**Decision required (Phase 1 output):**
- What are the canonical mutation operations? (examples: remove_evidence_class, inject_conflict, add_misleading_field, corrupt_syntax)
- How do you validate mutations produce valid data? (parseable logs? valid JSON? correct structure?)
- How do family overrides work? (per-fixture custom mutations?)

**Recommendation:** Build a `FixtureTransformer` class with predefined operations (`remove_evidence_class`, `inject_conflict`, `reorder_by_field`, `duplicate_record`, `corrupt_field`). Each operation validates output before running tests.

## Gap #5: E2E Structured Answer Type — REQUIRED, not Recommended

**The problem:** Phase 4 recommends `EvidenceAnswer` but doesn't require it. Tests might scrape prose instead.

**Decision required (Phase 1 output):**
- Define `EvidenceAnswer` dataclass as a **required internal type** (even if CLI still emits text).
- Design CLI → `EvidenceAnswer` mapping layer.
- Specify how structured answers are serialized (JSON? pickle? text representation?).

**Recommendation:** `EvidenceAnswer` is **in scope for Phase 4 implementation**, not a future enhancement. E2E tests assert against structured answers, not text parsing.

## Gap #6: Fixture Versioning & Schema Migration

**The problem:** "Update all atomically" doesn't scale. As fixtures grow (5 → 50+), schema changes become coordination chaos.

**Decision required (Phase 1 output):**
- How do you handle backward compatibility? (add optional fields? version the dataclass? migrate on load?)
- What tooling supports bulk updates? (script to auto-add new fields? validation to catch stale fixtures?)

**Recommendation:** Add a `__version__` field to fixture dataclass. When schema changes, provide a migration script (`tests/helpers/migrate_fixtures.py`) that updates all fixtures atomically. Fixtures are versioned in git history, not separate from code.

## Gap #7: Fixture Maintenance & Curation Labor

**The problem:** Plan says "every important bug becomes a fixture" but doesn't budget acquisition/reduction time.

**Decision required (Phase 1 output):**
- What's the process for turning a bug into a fixture? (capture live session? minimize?)
- Who reduces/minimizes fixtures? (automated tools? manual review?)
- How do you validate a fixture is stable and reproducible?

**Recommendation:** Allocate ~1-2 hours per fixture for acquisition, minimization, metadata writing. Provide `tests/helpers/fixture_reducer.py` to help minimize captured sessions. Fixtures require code review before merge.

## Gap #8: Contract Tests vs Invariants vs Implementation

**The problem:** Contract tests might just encode current behavior instead of actual contracts.

**Decision required (Phase 1 output):**
- What's non-negotiable across refactors? (list these explicitly in requirements doc)
- What's implementation detail? (don't test this)
- What's aspirational? (don't test this yet; defer to future phases)

**Recommendation:** Phase 1 requirements doc explicitly categorizes each requirement as "contract (non-negotiable)" or "implementation guideline." Contract tests only test contracts.

## Gap #9: Fixture Feedback Loop — Phase 1 Output Must Be Binding

**The problem:** If Phase 1 (requirements) reveals the system doesn't match the intended model, Phase 3 fixtures become aspirational.

**Decision required (Phase 1 output):**
- If a requirement can't be met by current code, flag it as "future work" in Phase 1 output.
- Don't design Phase 3 fixtures around aspirational requirements.

**Recommendation:** Phase 1 output includes an "Aspirational vs. Achievable" section. Fixtures are designed only around achievable requirements.

## Gap #10: Product Ownership & Incentive Alignment

**The problem:** Tests protect against drift, but don't prevent organizational pressure to "just infer," "lose provenance for speed," etc.

**Decision required (Phase 1 output):**
- Who makes trade-off decisions when tension arises? (feature speed vs. evidence completeness?)
- What's the policy if a requirement conflicts with a business need? (honor the requirement and defer the feature? find a third way?)

**Recommendation:** Document "Invariant Owner" and "Trade-off Authority" in requirements. If DebugOracle must ever break an invariant, that decision is escalated (not decided by implementers during feature work).

## Gap #11: Determinism Fuzzer False Positives

**The problem:** Fuzzer will fail on legitimate variation (dict ordering, float rounding, etc.) unless the contract is precise.

**Decision required (Phase 1 output):**
- Define exactly which fields are allowed to vary (timestamps? IDs? ordering?).
- Design the comparison logic upfront (canonical JSON? field-by-field comparison?).

**Recommendation:** Phase 1 includes a "Determinism Contract" section that defines allowed variance and the comparison algorithm. Fuzzer logic is spec'd before implementation.

---

# 3. Phase 1 — Write explicit testing requirements (UPDATED)

## Objective

Create a durable requirements document that translates the product model into testable statements.

## Deliverable

Add a file such as:

- `docs/specs/testing.md`
- or `docs/specs/test_requirements.md`

This file should define what the test system is supposed to protect.

## Why this comes first

Without explicit requirements, tests tend to mirror current code structure.  
That creates brittle tests and blind spots.

A requirements document does three things:
1. makes quality expectations visible
2. helps future contributors write the right tests
3. anchors later fixture and e2e design in product behavior, not implementation accident

## What the requirements document should contain

**CRITICAL: This document must be binding.** If it reveals gaps in current implementation, those gaps are surfaced but not hidden. Phases 3-5 depend on Phase 1 output being accurate and achievable.

At minimum:

### A. Testing scope
Define the layers of testing:
- unit
- contract
- integration
- replay/golden
- end-to-end question-centric
- HIL

Clarify what each layer is responsible for.

### B. Core invariant requirements
Translate each invariant into explicit testable requirements.

Examples:

#### Determinism
- identical inputs and configuration must produce identical artifacts
- identical CLI invocation on identical workspace state must produce identical output bytes and exit code
- output ordering must be stable

#### Evidence-first
- every public conclusion must be traceable to one or more source records
- artifacts must not contain unmarked guessed or inferred target state
- missing source evidence must not be silently filled in

#### Read-only by default
- default flows must not mutate target systems, live debuggers, or source evidence inputs
- commands must not perform implicit control actions
- outputs may only be written to approved workspace/output locations

#### Reproducibility
- persisted artifacts must support offline re-rendering/re-analysis without requiring live acquisition
- provenance must be sufficient to reconstruct why a conclusion was produced

#### Explicit provenance
- every derived field must carry source linkage
- renderers must preserve provenance visibility where required by the public contract

### C. Uncertainty requirements
This section is especially important and should be stronger than it often is in normal software projects.

Add requirements such as:
- insufficient evidence must produce `unknown` or equivalent explicit state
- conflicting evidence must be surfaced as conflict, not flattened into certainty
- reports must distinguish observed state from interpreted state
- “not observed” must not be rewritten as “false”

### D. Security and safety requirements
Because the guide explicitly mentions them, make them test requirements:
- no `shell=True`
- validate paths
- restrict file access to intended boundaries
- reject path traversal
- do not write outside approved workspace/output roots
- do not mutate persisted artifacts after creation

### E. Public behavior change policy
Document that:
- changed public behavior requires test updates
- changed public contracts may require spec updates
- snapshot changes alone are not sufficient justification

### F. Determinism Contract (CRITICAL FOR TESTING)
Define precisely:
- Which artifact fields are allowed to vary across runs? (timestamps? session IDs? list ordering?)
- What's the comparison algorithm? (byte-identical JSON? canonical form? semantic equivalence?)
- How are "unstable" fields handled in fixtures? (frozen to empty string? randomized-but-captured?)

Example:
```
REQ-DET-DETERMINISM-CONTRACT:
Fields allowed to vary: None (all fields byte-identical).
Allowed implementation detail: Timestamps in fixtures are frozen to "" (empty string).
Comparison: Canonical JSON (sorted keys, consistent formatting).
Fuzzer behavior: If any run differs from the canonical output, test fails (merge blocker).
```

### G. Fixture Format Specification (CRITICAL FOR PHASE 3)
Define:
- Fixture artifact format (frozen Python dataclass? JSON? YAML?)
- Where large data lives (separate `.log`/`.json` files? embedded in dataclass?)
- Metadata format (inline? separate `.meta.py` file? YAML file?)
- How fixtures are loaded, versioned, and migrated

Example:
```
FIXTURE_FORMAT_SPEC:
- Fixtures are frozen Python dataclasses in tests/fixtures/{name}/fixture.py
- Raw data (logs, registers) stored as .json or .log files in tests/fixtures/{name}/data/
- Metadata in tests/fixtures/{name}/metadata.py (questions, expected conclusions, required evidence)
- Versioning: __version__ field in dataclass, migration script for schema changes
```

### H. Metamorphic & Adversarial Oracle Specs (CRITICAL FOR PHASE 5)
Define the metamorphic transformation relationships:
- `add_irrelevant_noise`: conclusion state preserved, confidence may lower
- `reorder_non_semantic_records`: semantic equivalence after canonicalization
- `remove_essential_evidence`: conclusion degrades to unknown (not false positive)
- etc.

Define adversarial transformations:
- `inject_conflict`: evidence contradicts, surface conflict
- `remove_evidence_class`: missing evidence, degrade gracefully
- `corrupt_field`: malformed input, explicit error

Example:
```
METAMORPHIC_ORACLE_add_irrelevant_noise:
Input: fixture F with conclusion C (yes/no/unknown)
Transform: Add unrelated RTT lines
Expected: Conclusion state unchanged, but confidence may decrease
Test assertion: assert transformed_conclusion in ["yes", "no", "unknown"] and original_conclusion in ["yes", "no", "unknown"]
```

### I. Structured Answer Type Spec (REQUIRED FOR PHASE 4)
Define `EvidenceAnswer` as a required internal type:
```python
@dataclass(frozen=True)
class EvidenceAnswer:
    question: str
    conclusion: str  # yes/no/unknown
    confidence: str  # high/medium/low
    supporting_evidence: tuple[str, ...]  # references to evidence records
    missing_evidence: tuple[str, ...]  # what was needed but absent
    conflicts: tuple[str, ...]  # conflicting evidence sources
```

Specify:
- How CLI output maps to EvidenceAnswer (parsing/serialization)
- Invariants: conclusion must match confidence (high confidence → yes/no, medium/low → unknown possible)
- Requirement: E2E tests assert against structured answers, not text parsing

### J. Fixture Curation Process (LABOR & TOOLING)
Define:
- How bugs become fixtures (capture, minimize, validate, review)
- Tooling provided (fixture reducer? fuzzer?)
- Time budget per fixture (~1-2 hours)
- Quality gates (reproducible? minimal? well-documented?)

### K. Product Ownership & Invariant Steward
Define:
- Who owns the invariants? (who approves breaking changes?)
- Escalation path if business needs conflict with invariants
- Trade-off decision authority

## Recommended format

Use requirement IDs so they can be referenced in tests:

- `REQ-DET-001`
- `REQ-EVD-003`
- `REQ-UNC-002`
- `REQ-SAFE-004`

This gives structure and makes future gaps easier to identify.

## Example requirement style

Good:
- `REQ-UNC-001: If evidence required for a public conclusion is absent, the system must return an explicit unknown/insufficient-evidence state rather than a guessed conclusion.`

Weak:
- `System should maybe avoid guessing.`

Use precise, testable language.

---

# 4. Phase 2 — Create contract tests for the core invariants

## Objective

Add a dedicated test layer for product invariants, independent of local implementation structure.

## Deliverable

Create:

- `tests/contracts/`

Initial target: 5–10 high-value tests.

## Why contract tests matter

Contract tests protect behavior that must remain true even if:
- modules are refactored
- parsers are rewritten
- rendering changes
- new commands are added
- internal data flow evolves

They are a good fit for DebugOracle because the product is defined more by invariants than by exact architecture.

## Initial contract test families

### 4.1 Deterministic artifact generation
Test:
- given fixed input fixture and fixed configuration, artifact output is byte-identical across repeated runs

Implementation notes:
- use canonical JSON serialization if needed
- remove unstable fields or make them explicit and deterministic
- avoid timestamps unless intentionally part of the artifact and controlled

Why this matters:
- determinism is central to trust and replayability
- if this fails, debugging becomes non-reproducible and regression testing weakens

### 4.2 Provenance completeness
Test:
- all derived records in public artifact structures include required provenance metadata

Implementation notes:
- write traversal helpers that inspect artifact objects generically
- fail if provenance fields are missing, empty, or invalid

Why this matters:
- provenance is the backbone of evidence-first behavior
- without it, the system becomes a black-box summarizer

### 4.3 Unknown on missing evidence
Test:
- when a required evidence source is absent, the result remains unknown instead of silently concluding yes/no

Implementation notes:
- use a small synthetic fixture with one intentionally removed input
- assert structured result state if available; otherwise assert stable textual markers

Why this matters:
- prevents the most dangerous agent-style failure: overclaiming under ambiguity

### 4.4 Read-only default behavior
Test:
- default commands do not modify input evidence files or invoke control-side operations

Implementation notes:
- run against temp workspace
- snapshot file mtimes / hashes before and after
- monkeypatch control pathways to fail if touched

Why this matters:
- protects the product boundary between observation and intervention

### 4.5 Path and file access safety
Test:
- reject traversal or invalid output paths
- ensure writes stay inside expected workspace/output location

Why this matters:
- this is both a correctness and security boundary
- also useful for agentic workflows where path misuse can happen easily

### 4.6 Artifact immutability semantics
Test:
- persisted artifacts are not mutated after creation
- replacement behavior is explicit

Why this matters:
- supports reproducibility and auditability

## Guidance on test style

Contract tests should:
- avoid overfitting to module internals
- operate through public interfaces or stable core APIs
- check behavior, not incidental helper structure

---

# 5. Phase 3 — Build replayable fixtures from real debug sessions

## Objective

Create a small, high-quality fixture corpus from real sessions to protect against regressions in real-world behavior.

## Deliverable

Create something like:

- `tests/fixtures/`
- `tests/replay/`

Initial target: 3–5 fixtures.

## Why replay fixtures matter

Replay fixtures are one of the highest-value assets for this kind of product.

They:
- capture real complexity
- reduce dependence on synthetic examples
- let bugs become permanent regression tests
- protect against subtle drift in parsers, reducers, renderers, and agent-facing outputs

## What makes a good first fixture

Choose fixtures that represent distinct reasoning situations, not just different log files.

Recommended initial set:

### Fixture A — sufficient evidence, correct configuration
Purpose:
- prove the happy path works
- validate that the system can support a confident grounded answer

### Fixture B — sufficient evidence, incorrect configuration
Purpose:
- ensure the system can detect mismatch and explain it from evidence

### Fixture C — missing critical evidence
Purpose:
- ensure it degrades to unknown instead of guessing

### Fixture D — conflicting evidence sources
Purpose:
- ensure conflict is surfaced honestly

### Fixture E — noisy/irrelevant session
Purpose:
- ensure extra noise does not corrupt the conclusion

## Fixture contents

Each fixture should contain only the minimum required material.

For example:

- raw GDB MI log
- RTT log
- memory/register dumps
- optional doc snippet/reference fragment if relevant
- expected artifact outputs or expected structured properties
- one or more test questions

Avoid huge fixtures at first.  
Minimized fixtures are easier to understand and maintain.

## Fixture design guidance

Each fixture should answer:
1. what engineering situation is represented?
2. what conclusion should the system support?
3. what evidence is required for that conclusion?
4. what must the system not say?

## Recommended fixture metadata format

Consider a metadata file per fixture:

```yaml
name: spi_mode_mismatch
description: Live register state shows SPI mode differs from intended configuration.
questions:
  - id: q1
    prompt: "Is SPI1 configured as intended?"
    expected_conclusion: "no"
    required_evidence:
      - "spi_registers"
      - "intended_config_reference"
    forbidden_behaviors:
      - "claiming success without register evidence"
      - "guessing intended mode from naming only"
```

This makes later e2e tests much easier to build.

## Important discipline

Every time a real bug is found:

1. capture or reduce the session into a fixture
2. add the expected behavior
3. keep it permanently in regression coverage

That process compounds product quality over time.

---

# 6. Phase 4 — Add question-centric end-to-end tests

## Objective

Test the product in the form it is actually used:

> captured evidence + engineering question -> grounded answer
> 

## Deliverable

Create:

- `tests/e2e_questions/`

Initial target: 1–3 questions per replay fixture.

## Why this layer matters

DebugOracle’s value is not that it parses things.

Its value is that it helps answer engineering questions from evidence.

A suite that never tests question answering is missing the product surface.

## Key design idea

The test unit is not just input/output. It is:

- fixture
- question
- expected conclusion
- required evidence classes
- forbidden claims
- expected uncertainty behavior

This makes the tests much closer to actual agentic usage.

## Good first question categories

### Configuration validation

- “Is SPI configured as intended?”
- “Does the ADC trigger source match the expected timer?”

### Mismatch detection

- “Do the observed registers match initialization intent?”

### Fault localization support

- “Is there evidence that this fault is caused by interrupt latency?”

### Insufficient evidence handling

- “Can this conclusion be made from the current capture?”

## Assertion strategy

Avoid relying only on exact string matching.

Prefer assertions on:

- conclusion state (`yes`, `no`, `unknown`)
- supporting evidence presence
- conflict reporting
- uncertainty markers
- absence of unsupported claims

If the system only emits text today, consider adding a structured intermediate answer type in future.

## CRITICAL: Structured Answer Type is REQUIRED for Phase 4

**This is not optional.** Phase 4 e2e tests MUST work against structured answers, not text parsing.

Implement:

```python
@dataclass(frozen=True)
class EvidenceAnswer:
    question: str
    conclusion: str  # yes/no/unknown (REQUIRED)
    confidence: str  # high/medium/low (REQUIRED)
    supporting_evidence: tuple[str, ...]  # evidence record IDs
    missing_evidence: tuple[str, ...]  # evidence classes needed
    conflicts: tuple[str, ...]  # conflicting sources
    notes: tuple[str, ...]  # human-readable explanation
```

Invariants:
- `conclusion` must be in {yes, no, unknown}
- `confidence: high` implies `conclusion in {yes, no}` (not unknown)
- `confidence: low` or `medium` allows any conclusion
- E2E tests assert against these fields, not text output

Why this is required:

- Decouples tests from rendering details (CLI output format can change without breaking e2e tests)
- Makes confidence/conclusion contracts explicit and testable
- Supports future agent consumption without prose parsing
- Makes it impossible to lose evidence tracing in output

Implementation approach:
1. Define `EvidenceAnswer` in Phase 4
2. Create `internal_to_answer()` function that converts internal state to structured answer
3. Specify how CLI renders `EvidenceAnswer` to text (separate concern)
4. E2E tests run against answer, not text

**Exit criteria:** All e2e assertions are on `EvidenceAnswer` fields, never on text parsing.

---

# 7. Phase 5 — Add adversarial and metamorphic tests before broad scaling

## Objective

Protect trustworthiness and robustness before expanding raw fixture count.

## Deliverable

Create:

- `tests/adversarial/`
- `tests/metamorphic/`

Initial target:

- 3 metamorphic tests
- 3 adversarial tests

## Why this comes before scale

A large number of happy-path fixtures can create false confidence.

For agent-adjacent systems, some of the most serious failures happen when:

- inputs are incomplete
- evidence conflicts
- irrelevant information is present
- one source is malformed
- the system is tempted to guess

Adversarial and metamorphic tests target those risks directly.

## 7.1 Metamorphic tests (ORACLE-DRIVEN)

These test that non-semantic changes do not alter the core conclusion.

**Each metamorphic transformation has an oracle (expected relationship):**

### Add irrelevant noise
- Transform: add unrelated RTT lines
- Oracle: conclusion state (yes/no/unknown) preserved; confidence may lower
- Test: `assert transformed_answer.conclusion == original_answer.conclusion`
- Why: irrelevant data should not corrupt the conclusion

### Reorder non-semantic records
- Transform: reorder log segments where order shouldn't matter
- Oracle: semantic equivalence (same evidence, different order → same conclusion)
- Test: `assert canonical(transformed_answer) == canonical(original_answer)`
- Why: implementation shouldn't be order-dependent

### Duplicate evidence lines
- Transform: duplicate non-unique entries (e.g., same register read twice)
- Oracle: conclusion and confidence unchanged
- Test: `assert transformed_answer == original_answer` (after canonicalization)
- Why: duplicates are noise, not new information

### Remove non-essential evidence
- Transform: remove an evidence source that wasn't required for the conclusion
- Oracle: conclusion stays the same
- Test: identify essential sources first; remove non-essential; assert conclusion unchanged
- Why: unused evidence shouldn't support conclusions

### Remove essential evidence
- Transform: remove evidence that IS required for the conclusion
- Oracle: conclusion degrades to unknown (not stays yes/no by guessing)
- Test: identify essential sources; remove one; assert conclusion becomes unknown
- Why: prevents overclaiming when evidence is missing

Why these matter:

- they reveal brittle or overfit logic
- they make the system safer in messy real sessions
- they directly test robustness under realistic data variation

## 7.2 Adversarial tests (TRANSFORMATION DSL)

These test whether the system resists misleading inputs.

**Each adversarial test uses a transformation from a fixture transformer DSL:**

### Transformation Operations

Build `tests/helpers/fixture_transformers.py` with:

```python
class FixtureTransformer:
    @staticmethod
    def remove_evidence_class(fixture, evidence_class):
        “””Remove all evidence of a given class (e.g., 'registers')”””
        # Return new fixture with that evidence removed
        # Validate result is still a valid fixture

    @staticmethod
    def inject_conflict(fixture, field_path, new_value):
        “””Inject contradictory evidence (e.g., registers say SPI=1, docs say SPI=0)”””
        # Return new fixture with conflict injected

    @staticmethod
    def corrupt_field(fixture, field_path, corruption_type):
        “””Corrupt a field (e.g., truncate, scramble, delete)”””
        # corruption_type: 'truncate', 'scramble', 'null'

    @staticmethod
    def add_misleading_field(fixture, field_name, misleading_value):
        “””Add a field with misleading/contradictory content”””
        # E.g., add a signal name that implies something unsupported by data

    @staticmethod
    def remove_context(fixture, context_field):
        “””Remove contextual information (e.g., device datasheet, intended config)”””
        # Simulates “missing documentation” scenario
```

All transformations validate output is still parseable.

### Good Examples (with oracles)

#### Conflicting sources

- Transform: `inject_conflict(“spi_config”, observed=1, intended=0)`
- Oracle: Result must surface conflict; conclusion is either “no (with conflict evidence)” or “unknown”
- Test: `assert “conflict” in transformed_answer.conflicts or transformed_answer.conclusion == “unknown”`
- Why: Conflicting evidence should never be silently resolved

#### Misleading names

- Transform: Add a signal name that doesn't match evidence (e.g., name=”SPI1_EN” but register shows different pin)
- Oracle: System must not treat name as proof; conclude based only on evidence
- Test: `assert transformed_answer == original_answer` (names don't change evidence)
- Why: Names can be misleading; evidence is truth

#### Partial state

- Transform: `remove_evidence_class(“register_dumps”)`
- Oracle: If registers were essential, conclusion degrades to unknown; if not, unchanged
- Test: Identify essential sources; remove them; assert conclusion becomes unknown
- Why: Prevents overclaiming when evidence is incomplete

#### Malformed source chunk

- Transform: `corrupt_field(“gdb_mi_logs”, corruption_type='truncate')`
- Oracle: Parser handles gracefully; either skips malformed input or fails explicitly
- Test: Assert DebugOracle returns a clear error, not silent misparse
- Why: Robustness against corrupted input

#### Stale or irrelevant docs

- Transform: `remove_context(“device_datasheet”)`
- Oracle: Conclusion either stays the same (didn't depend on docs) or degrades (did depend)
- Test: `assert “updated: unknown” in transformed_answer or transformed_answer == original_answer`
- Why: Prevents relying on potentially stale documentation

### Adversarial Coverage Matrix

After implementing a few adversarial tests, build a matrix:

```
Fixture Family  | inject_conflict | remove_evidence | corrupt_field | add_misleading | remove_context
────────────────┼─────────────────┼─────────────────┼───────────────┼────────────────┼────────────────
spi_mode_match  | ✓               | ✓               | ✓             | ✓              |
spi_mode_mismatch| ✓              | ?               | ?             | ?              |
missing_evidence| —               | ✓               | —             | —              | ✓
conflicting_src | ✓               | —               | —             | —              | —
noisy_session   | ✓               | ✓               | ✓             | ✓              | ?
```

Goal: Ensure every fixture family is tested under at least 3-4 adversarial conditions.

Why these matter:

- they directly protect against “looks plausible” failures
- they are highly relevant in agentic coding environments
- they force the system to be robust, not just correct on happy paths

---

# 8. Requirements strengthening guidance

This section adds requirements guidance beyond the original step list, because stronger requirements will produce better tests and a better product.

## 8.1 Add “claim discipline” requirements

This should be a formal requirement area.

Suggested requirements:

- public claims must distinguish observed facts from derived interpretations
- interpretations must name their evidence basis
- uncertainty must be first-class, not treated as failure
- unsupported causal claims are forbidden
- absence of evidence must not be rewritten as evidence of absence unless explicitly justified

This is especially important if future agents consume DebugOracle output directly.

## 8.2 Add “evidence sufficiency” requirements

For important question types, define what evidence classes are minimally sufficient.

Examples:

- register-based configuration claims require relevant live register evidence
- intent-vs-observed claims require both observed state and intent source
- timing/trigger chain claims may require more than one source class

This helps prevent “one weak clue becomes a conclusion.”

## 8.3 Add “conflict handling” requirements

Explicitly define what must happen if evidence conflicts.

Possible requirement style:

- conflicts must be surfaced, not silently collapsed
- if conflict resolution policy exists, it must be explicit
- if conflict prevents confident conclusion, result must degrade accordingly

## 8.4 Add “structured output” requirements

Even if current output is mainly CLI text, define requirements for structured internal representations.

Reason:

- better tests
- easier future integrations
- safer agent consumption
- more deterministic assertions

## 8.5 Add “minimality” requirements

Since token discipline is part of the product philosophy, add requirements like:

- reports should include sufficient evidence, not unbounded dumps
- summaries should not omit required support
- irrelevant input should not dominate output
- retrieval/reduction should prefer minimal sufficient context

This helps the product stay aligned with the guide, not just technically correct.

---

# 8.6 Fixture Curation & Maintenance (Labor Estimate)

Building fixtures is not free. The plan says "every important bug becomes a fixture," but this requires labor.

## Fixture Acquisition Process

For each real bug that becomes a fixture:

1. **Capture** (~15 min): Reproduce the bug, capture the DebugOracle session (GDB MI logs, RTT, registers, etc.)
2. **Minimize** (~30-45 min): Remove noise and irrelevant data to create a minimal reproduction. Tools: `tests/helpers/fixture_reducer.py` (automated trim) + manual review.
3. **Validate** (~15 min): Run DebugOracle on the minimized fixture multiple times. Confirm it reproduces the bug consistently and is deterministic.
4. **Document** (~15 min): Write metadata (questions, expected conclusions, required evidence, forbidden behaviors).
5. **Review** (~15 min): Code review the fixture to ensure it's accurate and will be useful long-term.

**Total per fixture: ~1.5–2 hours.**

## Fixture Maintenance

When the DebugOracle schema changes (new fields in EvidenceBundle, artifact structure updates):
- Fixtures must be updated atomically
- Provide migration script (`tests/helpers/migrate_fixtures.py`) to automate bulk updates
- Run all tests to verify fixtures still work

**Cost: ~30 min per schema change (with tooling)**

## Tooling Requirements (In Scope for Phase 3)

Provide these helpers to reduce curation cost:

```
tests/helpers/
  fixture_reducer.py       # Automated fixture minimization
  fixture_validator.py     # Validate fixture is deterministic and reproducible
  fixture_migrator.py      # Bulk schema migration
  fixture_loader.py        # Common loading/deserialization
  artifact_assertions.py   # Reusable assertion helpers
```

These reduce per-fixture curation time from 2 hours to ~1.5 hours over time.

## Fixture Corpus Growth Estimate

- Phase 3 initial: 3–5 fixtures (~5–10 hours labor)
- Per quarter: ~1–2 new fixtures from bugs caught (~2–4 hours/quarter)
- Year 1 target: ~10–15 fixtures total

This is sustainable.

---

# 8.7 Product Ownership & Invariant Stewardship

Tests protect against drift, but only if there's organizational commitment to the invariants.

## The Risk

Over time, pressure to "ship faster" or "be more helpful" can push DebugOracle away from its core model:
- "Just infer the missing register value" (breaks evidence-first)
- "Optimize for token count even if we lose provenance" (breaks completeness)
- "Add a confidence score to make the output look more authoritative" (breaks simplicity)
- "Skip provenance tracking when evidence is obvious" (breaks auditability)

Tests alone cannot prevent these choices. But clear ownership can.

## Solution: Explicit Invariant Stewardship

Add to Phase 1 output:

### Who Owns Each Invariant?

- **Determinism owner:** Reviews any changes to artifact generation, serialization, or caching. Approves any non-deterministic behavior.
- **Evidence-first owner:** Reviews any changes to output rendering or conclusion logic. Rejects inferred or guessed state.
- **Provenance owner:** Reviews any code that traverses or renders evidence trails. Rejects code that loses source linkage.
- **Read-only owner:** Reviews any commands that interact with targets or modify input files. Enforces read-only semantics.

### Escalation Path for Trade-Offs

If a business need conflicts with an invariant, escalate to [product lead / architecture lead]. Examples:

- "We want to guess missing evidence to be more helpful"
  → Escalate. Options: (a) honor evidence-first, reject feature; (b) add an explicit `--guess` flag (breaks contract); (c) find different approach.

- "Provenance tracking adds 2KB per report"
  → Escalate. Options: (a) accept the cost; (b) compress provenance; (c) use lazy provenance.

### How Tests Protect Ownership

Each invariant has contract tests. If someone tries to break the invariant (even "just for this feature"), tests fail and block merge. This forces the conversation to happen explicitly.

---

# 9. Proposed repository additions

Suggested additions:

```
docs/
  specs/
    testing.md

tests/
  contracts/
  replay/
  e2e_questions/
  adversarial/
  metamorphic/
  fixtures/
    spi_mode_match/
    spi_mode_mismatch/
    missing_evidence/
    conflicting_sources/
    noisy_session/
```

Optional support helpers:

```
tests/
  helpers/
    artifact_assertions.py
    provenance_assertions.py
    fixture_loader.py
    answer_assertions.py
```

These helpers reduce duplication and make the suite easier to expand.

---

# 10. Suggested implementation order

## CRITICAL SEQUENCING RULE

**Phase 1 output is binding and gates Phases 3-5.** Do NOT proceed to Phase 3 (fixtures) until Phase 1 specifications are complete and agreed. If Phase 1 reveals gaps (current code doesn't support a requirement), either:
- Defer the requirement to future work (and don't design Phase 3 fixtures around it), OR
- Add the capability to Phase 1 scope (e.g., implement EvidenceAnswer if it doesn't exist)

Phase 2 (contract tests) can proceed in parallel with Phase 1 (they inform each other). But Phase 3 waits for Phase 1 to be binding.

## Step 1 — Write test requirements spec (PHASE 1 — BINDING GATES PHASE 3-5)

Create `docs/specs/testing.md`.

Exit criteria (ALL REQUIRED before moving to Phase 3):

- core invariants translated into requirement IDs with REQ-* identifiers
- uncertainty and conflict handling documented
- testing layers and responsibilities described
- **[CRITICAL]** Determinism contract defined (allowed variance, comparison algorithm)
- **[CRITICAL]** Fixture format specification locked in (dataclass, metadata, large data storage)
- **[CRITICAL]** Metamorphic oracle for each transformation (what stays the same? what changes?)
- **[CRITICAL]** Adversarial transformation DSL defined (remove_evidence_class, inject_conflict, corrupt_field, etc.)
- **[CRITICAL]** EvidenceAnswer dataclass designed and specified (required, not optional)
- Fixture curation process documented (acquisition, minimization, validation, review)
- Fixture versioning & migration strategy defined
- Invariant ownership assigned (who owns determinism? evidence-first? provenance? read-only?)
- Trade-off escalation path specified (what happens when business needs conflict with invariants?)

## Step 2 — Add first contract tests

Create `tests/contracts/` and implement 5–10 tests.

Priority order:

1. deterministic outputs
2. provenance completeness
3. unknown on missing evidence
4. read-only default
5. path safety

Exit criteria:

- core invariant failures would now break CI

## Step 3 — Create first replay fixtures

Build 3–5 minimized real-world fixtures.

Exit criteria:

- each fixture has metadata
- each fixture captures a distinct reasoning scenario
- fixture loading is stable and easy to understand

## Step 4 — Add question-centric e2e tests

For each fixture, add 1–3 key engineering questions.

Exit criteria:

- question-level behavior is now regression tested
- suite checks groundedness, not just parser output

## Step 5 — Add metamorphic and adversarial coverage

Start with a small set and expand over time.

Exit criteria:

- suite now tests robustness under noise, ambiguity, and conflict
- overclaiming regressions become visible

## Step 6 — Turn real bugs into replay fixtures

Adopt a maintenance rule:

- every important bug should become a replay or adversarial test

Exit criteria:

- regressions compound into long-term product hardening

---

# 11. Review criteria for implementation quality

When reviewing the implementation of this plan, ask:

## Requirements quality

- Are requirements precise and testable?
- Do they define uncertainty and conflict clearly?
- Do they reflect the actual product promise?

## Test usefulness

- Would these tests catch trust-breaking failures?
- Do they protect against overclaiming?
- Do they survive normal refactoring?

## Fixture quality

- Are fixtures real enough to matter?
- Are they minimized enough to maintain?
- Does each fixture teach one important lesson?

## Product alignment

- Does the test suite reinforce DebugOracle as an evidence system?
- Does it discourage drift toward hidden inference or non-deterministic summarization?
- Does it improve safety for agentic usage?

---

# 12. Non-goals for this phase

To keep the implementation disciplined, these are not the immediate goal:

- achieving high raw line coverage as the primary metric
- building a huge fixture corpus immediately
- perfecting HIL coverage before offline replay quality is strong
- over-engineering a generalized eval framework before core contract tests exist
- rewriting the whole architecture to fit the tests

The first win is not test quantity.

It is locking in the product invariants and trust model.

---

# 13. Final implementation principle

The testing system should make it hard for DebugOracle to become:

- nondeterministic
- ungrounded
- overconfident
- hard to replay
- weakly auditable
- overly “helpful” in the absence of evidence

It should make it easy for DebugOracle to remain:

- deterministic
- evidence-first
- reproducible
- provenance-rich
- honest under ambiguity
- safe to use in agentic debugging workflows

---

# 14. REVISIONS & CLARIFICATIONS (CEO Review Round)

## What Changed

This plan was updated after an independent outside voice review that identified 11 specification gaps. The gaps were not rejections of the plan but critical clarifications needed before implementation.

### Gaps Addressed

1. **Fixture Format** — Clarified: frozen Python dataclasses, metadata in separate `.py` files, raw data in `.json`/`.log` files
2. **Determinism Contract** — Defined: allowed variance (timestamps frozen), comparison algorithm (canonical JSON)
3. **Fixture Versioning** — Specified: `__version__` field, migration scripts for schema changes
4. **Metamorphic Oracles** — Documented: for each transformation, what stays the same (conclusion? confidence? both?)
5. **Adversarial Transformation DSL** — Designed: reusable transformers (remove_evidence_class, inject_conflict, corrupt_field, etc.)
6. **EvidenceAnswer Type** — Changed from "recommended" to **REQUIRED** for Phase 4
7. **Metamorphic Test Oracles** — Made explicit (added oracle column to each transformation)
8. **Fixture Maintenance Cost** — Estimated: ~1.5–2 hours per fixture, with tooling to reduce burden
9. **Fixture Curation Tooling** — Added to scope: reducer, validator, migrator scripts
10. **Product Ownership** — Added section: invariant stewards, escalation path for trade-offs
11. **Phase 1 as Binding Gate** — Clarified: Phases 3-5 cannot start until Phase 1 specifications are locked in

### Why These Clarifications Matter

The original plan was solid in strategy but vague in execution. These clarifications transform it from aspirational to implementable:

- **Before:** "Add fixtures from real sessions" → **After:** "Fixtures are frozen dataclasses in tests/fixtures/{name}/, acquired via [specific process], validated before merge"
- **Before:** "Adversarial tests" → **After:** "Adversarial tests use FixtureTransformer DSL with [specific operations]"
- **Before:** "EvidenceAnswer is recommended" → **After:** "EvidenceAnswer is required; e2e tests assert against it, not text"
- **Before:** "Every bug becomes a fixture" → **After:** "Every bug becomes a fixture after [curation process], ~1.5–2 hours labor"

### Approach & Mode Confirmation

- **Approach:** B (Full Plan) — all 5 phases + 4 enhancements
- **Mode:** EXPANSION (ambitious, dreaming big while being explicit about specs)
- **Temporal Decisions:** 5 key decisions locked in (fixture format, e2e parameterization, adversarial strategy, CI integration, fixture storage)

### Completeness Assessment

This plan is now **8.5/10 for completeness**:
- ✅ Phases are well-sequenced
- ✅ Specifications are explicit and binding
- ✅ Tooling is in scope
- ✅ Labor estimates are realistic
- ✅ Ownership is clear
- ⚠️ Minor: Implementation details still TBD (exact pytest fixtures, conftest structure)

**Ready to implement:** Yes, after Phase 1 specs are written and locked in.