# DebugOracle — Testing Plan Phase 4: Question-Centric Eval Tests

**Status:** Proposal — future, non-binding
**Phase:** 4 (LLM Eval Tests)
**Source plan:** Legacy `docs/plans/testing_rework.md §6` (file removed; phased docs are canonical)
**Reviewed by:** `/plan-eng-review` 2026-03-27
**Gate:** Phase 3 fixtures must exist with `metadata.yaml` before proceeding

This is a design proposal, not a current delivery commitment. Prioritize work through
[`ROADMAP.md`](../../ROADMAP.md) before treating it as implementation scope.

---

## Context

Phase 3 provides a fixture corpus with per-fixture `metadata.yaml` containing
engineering questions, expected conclusions, and evidence requirements. Phase 4
tests the product in the form it is actually used:

> DebugOracle output (artifact) + engineering question → AI agent → structured answer

This phase is an **LLM eval**, not a unit test suite. The AI agent receives the
DebugOracle artifact and a question; the eval checks whether the agent's structured
answer matches the expected conclusion.

Target: 1–3 eval cases per replay fixture in `tests/evals/`.

---

## Architecture

```
tests/fixtures/{name}/metadata.yaml   ← questions + expected conclusions
tests/fixtures/{name}/expected.json   ← DebugOracle artifact (InvestigationArtifact)
        │
        ▼
Eval runner (new: tests/evals/runner.py)
  1. Load artifact via load_bundle()
  2. Render artifact to text (existing renderer)
  3. Call AI agent with: artifact text + question
  4. Parse agent response as EvidenceAnswer JSON
  5. Compare answer.conclusion to expected_conclusion
  6. Run 3 times per eval case; require 2/3 to pass
        │
        ▼
EvidenceAnswer (structured output schema)    ← agent MUST return this as JSON
        │
        ▼
Eval report: pass/fail per case, per run, aggregate score
```

**Note:** Evals are NOT part of the standard pytest CI run. They require an API
key and call the LLM. Run separately (`make evals` or `pytest tests/evals/
--run-evals`).

---

## EvidenceAnswer Schema

`EvidenceAnswer` already exists in `debugoracle/artifacts/models.py`. Phase 4
requires the following additions to that dataclass:

```python
@dataclass(frozen=True)
class EvidenceAnswer:
    question: str
    conclusion: str           # "yes" | "no" | "unknown"
    confidence: str           # "high" | "medium" | "low"
    evidence_sources: list[str] = field(default_factory=list)
    # ADDITIONS required for Phase 4:
    missing_evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
```

**Breaking change note:** `evidence_sources` keeps its current name (avoid
renaming to `supporting_evidence` to prevent breaking existing contract tests).

Invariants (enforced by eval harness):
- `conclusion` must be in `{"yes", "no", "unknown"}`
- `confidence == "high"` implies `conclusion in {"yes", "no"}` (never unknown)
- `confidence in {"medium", "low"}` allows any conclusion

---

## Eval Runner

`tests/evals/runner.py` — the eval harness:

```python
@dataclass
class EvalCase:
    fixture_name: str
    question_id: str
    question_prompt: str
    expected_conclusion: str   # "yes" | "no" | "unknown"
    required_evidence: list[str]
    forbidden_behaviors: list[str]

@dataclass
class EvalRunResult:
    run_index: int              # 1, 2, 3
    raw_response: str
    parsed_answer: EvidenceAnswer | None
    parse_error: str | None     # set if response was unparseable
    conclusion_match: bool

@dataclass
class EvalCaseResult:
    case: EvalCase
    runs: list[EvalRunResult]   # always 3 runs
    passed: bool                # True if >= 2/3 runs have conclusion_match=True

def run_eval_case(case: EvalCase, artifact: InvestigationArtifact) -> EvalCaseResult:
    ...
```

**Parse failure handling:** If the agent returns unparseable output (not valid
JSON, missing required fields, wrong schema), that run scores as `conclusion_match=False`
with `parse_error` populated. The 2/3 threshold still applies.

---

## Pass Threshold

- **3 runs** per eval case
- **2/3 runs** must have `conclusion_match=True` to pass
- A run passes if `parsed_answer.conclusion == case.expected_conclusion`
- Parse errors count as failed runs (not as harness errors)

Rationale: 2/3 is above the random baseline (~33% for 3-class output) while
tolerating natural model variation. Adjust threshold per case if needed.

---

## Eval Cases per Fixture

```
tests/evals/
  test_eval_fixture_a.py     # spi_mode_match
  test_eval_fixture_b.py     # spi_mode_mismatch
  test_eval_fixture_c.py     # missing_evidence
  test_eval_fixture_d.py     # conflicting_sources
  test_eval_fixture_e.py     # noisy_session
```

Each eval file loads `metadata.yaml`, iterates over questions, runs `run_eval_case()`,
and asserts the `EvalCaseResult.passed` field.

### Question Categories

**Configuration validation** (Fixtures A, B)
- "Is SPI configured as intended?"
- Assert: conclusion correct + `evidence_sources` non-empty

**Insufficient evidence** (Fixture C)
- "Can this conclusion be made from the current capture?"
- Assert: conclusion = `unknown` + `missing_evidence` non-empty

**Conflict surfacing** (Fixture D)
- "Do the observed registers match initialization intent?"
- Assert: conclusion = `unknown` or `no` + `conflicts` non-empty

**Noise resilience** (Fixture E)
- Same question as Fixture A but with noise
- Assert: conclusion matches Fixture A conclusion

---

## Assertion Strategy

Eval assertions are on `EvidenceAnswer` fields — never on text output:

| What to assert | Field | Example |
|---|---|---|
| Conclusion state | `answer.conclusion` | `assert answer.conclusion == "no"` |
| Named evidence | `answer.evidence_sources` | `assert len(answer.evidence_sources) > 0` |
| Missing evidence named | `answer.missing_evidence` | `assert "register_dump" in answer.missing_evidence` |
| Conflict reported | `answer.conflicts` | `assert len(answer.conflicts) > 0` |
| No overclaiming | composite | `assert not (answer.conclusion == "yes" and len(answer.evidence_sources) == 0)` |

---

## CI Integration

Evals are opt-in, not part of default CI:

```
# Run standard tests (no evals):
pytest tests/contracts/ tests/replay/

# Run evals explicitly:
pytest tests/evals/ --run-evals  (requires LLM_API_KEY env var)
```

A custom pytest marker `@pytest.mark.eval` marks each eval test. The `--run-evals`
flag (added via `conftest.py`) enables them.

---

## Support Helpers

```
tests/evals/
  runner.py       # EvalCase, EvalRunResult, EvalCaseResult, run_eval_case()
  conftest.py     # pytest marker + --run-evals flag
  loader.py       # load_eval_cases_from_metadata(fixture_path) -> list[EvalCase]
```

---

## Exit Criteria

- [ ] `EvidenceAnswer` dataclass extended with `missing_evidence`, `notes`,
      `conflicts` fields (in `debugoracle/artifacts/models.py`)
- [ ] Eval runner (`tests/evals/runner.py`) implemented with 3-run / 2/3 threshold
- [ ] Parse failures score as `parse_error`, count as failed run (not crash)
- [ ] 1–3 eval cases per fixture (5 fixtures × ~2 = ~10 eval cases)
- [ ] `--run-evals` pytest flag implemented; evals skipped in default CI
- [ ] All assertions are on `EvidenceAnswer` fields — no text parsing
- [ ] `confidence == "high"` invariant enforced: no high-confidence unknown
- [ ] Eval cases cover all 4 question categories (config, mismatch/conflict, insufficient, noise)

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR | 9 issues found, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**VERDICT:** ENG CLEARED — ready to implement.
