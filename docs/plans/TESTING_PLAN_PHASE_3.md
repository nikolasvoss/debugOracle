# DebugOracle — Testing Plan Phase 3: Replayable Fixtures

**Status:** Not started
**Phase:** 3 (Replay Fixtures)
**Source plan:** `docs/plans/testing_rework.md §5, §8.6`
**Reviewed by:** `/plan-eng-review` 2026-03-27
**Gate:** Phase 1 spec must be binding before proceeding (see sequencing rule in §10)

---

## Context

Phase 2 (contract tests) will be complete with 6 gap-filling tests in
`tests/contracts/`. Phase 3 builds a small, high-quality fixture corpus from
real sessions to protect against regressions in real-world behavior.

Target: 3–5 minimized fixtures in `tests/fixtures/` with replay tests in
`tests/replay/`.

---

## Architecture

```
Real debug session
        │
        ▼
Capture (GDB MI log, RTT log)
        │
        ▼
Minimize (manual — remove noise, irrelevant lines)
        │
        ▼
tests/fixtures/{name}/
  ├── expected.json    ← save_bundle() output of the expected InvestigationArtifact
  ├── metadata.yaml    ← questions, expected conclusions, required evidence
  └── data/
      ├── gdb.log      ← raw GDB MI log (source of truth for Phase 5 transforms)
      └── rtt.log      ← raw RTT log
        │
        ▼
tests/replay/          ← regression tests: load raw data, build_bundle_from_text(),
                          compare output to expected.json via load_bundle()
```

### Fixture format (updated from eng review)

```
FIXTURE_FORMAT_SPEC:
- Expected artifact: tests/fixtures/{name}/expected.json (save_bundle() output)
- Raw data: tests/fixtures/{name}/data/gdb.log + rtt.log
- Metadata: tests/fixtures/{name}/metadata.yaml
- Versioning: when InvestigationArtifact schema changes, re-run save_bundle()
  on each fixture's raw data to regenerate expected.json
```

**Rationale:** Using `save_bundle()`/`load_bundle()` JSON reuses existing
infrastructure and avoids fragile Python dataclass imports. Raw data files
are required for Phase 5 transformers (which operate on text, not artifacts).

---

## Step 0: Extract `_comparable()` first

Before writing any fixtures, extract the existing `_comparable()` helper from
`tests/contracts/test_core_invariants.py` into `tests/helpers/artifact_assertions.py`
and update the contract test to import it.

This is a trivial refactor (~5 min) that:
1. Validates the `tests/helpers/` directory setup
2. Gives Phase 3 replay tests a ready-to-use comparison helper
3. Removes duplication between contract tests and replay tests

```python
# tests/helpers/artifact_assertions.py
import dataclasses
from debugoracle.artifacts.models import InvestigationArtifact

UNSTABLE_FIELDS = {"captured_at", "snapshot_id"}

def comparable(artifact: InvestigationArtifact) -> dict:
    """Strip fields allowed to vary across runs before comparison."""
    d = dataclasses.asdict(artifact)
    for f in UNSTABLE_FIELDS:
        d.pop(f, None)
    return d
```

---

## Fixture Families

### Fixture A — sufficient evidence, correct configuration

**Scenario:** SPI registers match intended configuration.
**Purpose:** Happy path — prove a confident, grounded "yes" is reachable.
**Expected conclusion (metadata):** `yes`
**Required evidence:** live register snapshot + intended config reference
**Forbidden:** conclusion without register evidence

### Fixture B — sufficient evidence, incorrect configuration

**Scenario:** SPI registers differ from intended configuration.
**Purpose:** Mismatch detection — system explains discrepancy from evidence.
**Expected conclusion (metadata):** `no`
**Required evidence:** both observed and intended state
**Forbidden:** claiming match without register evidence

### Fixture C — missing critical evidence

**Scenario:** Register snapshot absent; only RTT logs present.
**Purpose:** Evidence-first degradation — system returns `unknown`, not a guess.
**Expected conclusion (metadata):** `unknown`
**Required evidence:** none that supports a yes/no
**Forbidden:** any confident yes/no without register evidence

### Fixture D — conflicting evidence sources

**Scenario:** Two sources disagree on SPI mode.
**Purpose:** Conflict is surfaced, not silently collapsed.
**Expected conclusion (metadata):** `unknown` or `no` with explicit conflict reported
**Required evidence:** conflicting sources both present
**Forbidden:** silent resolution of conflict

### Fixture E — noisy / irrelevant session

**Scenario:** Session contains many unrelated RTT lines alongside relevant data.
**Purpose:** Noise resilience — conclusion matches what a noise-free session produces.
**Expected conclusion (metadata):** same as the noise-free equivalent
**Forbidden:** noise causing conclusion drift

---

## Metadata Format

Each fixture carries `metadata.yaml`:

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

---

## Replay Test Structure

```
tests/replay/
  test_fixture_a.py
  test_fixture_b.py
  ...
```

Each replay test:
1. Reads raw data from `tests/fixtures/{name}/data/`
2. Runs `build_bundle_from_text()` (with patched timestamp)
3. Loads expected artifact via `load_bundle("tests/fixtures/{name}/expected.json")`
4. Compares with `comparable()` from `artifact_assertions.py`

Pattern:

```python
from tests.helpers.artifact_assertions import comparable
from debugoracle.artifacts.bundle import load_bundle
from debugoracle.builder import build_bundle_from_text
from unittest.mock import patch
from pathlib import Path
import unittest

FIXED_TIMESTAMP = "2024-01-01T00:00:00Z"

class TestFixtureA(unittest.TestCase):
    FIXTURE = Path("tests/fixtures/spi_mode_match")

    def test_artifact_matches_expected(self):
        mi = (self.FIXTURE / "data/gdb.log").read_text()
        rtt = (self.FIXTURE / "data/rtt.log").read_text()
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            result = build_bundle_from_text(mi, rtt)
        expected = load_bundle(str(self.FIXTURE / "expected.json"))
        self.assertEqual(comparable(result), comparable(expected))
```

**Note:** `expected.json` must be generated with the same patched timestamp
(`FIXED_TIMESTAMP`) when first created.

---

## Support Helpers (in scope for Phase 3)

```
tests/helpers/
  fixture_loader.py       # load_fixture_data(path) → (mi_text, rtt_text, metadata)
  artifact_assertions.py  # comparable(), assert_artifacts_equal()
```

**Deferred (not exit criteria):**
- `fixture_reducer.py` — manual minimization is sufficient at 3–5 fixtures
- `fixture_validator.py` — determinism is already covered by contract tests; add later
- `fixture_migrator.py` — needed only when schema changes; add when first change happens

---

## Fixture Curation Process

Per fixture (~1–1.5 hours total):

1. **Capture** (~15 min): Reproduce or construct the scenario; capture GDB MI
   and RTT text. Minimal real logs, or synthetic logs hand-crafted to represent
   the scenario.
2. **Minimize** (~20–30 min): Remove unrelated lines until the fixture is the
   smallest text that still exercises the scenario.
3. **Generate expected.json** (~5 min): Run `build_bundle_from_text()` with
   `FIXED_TIMESTAMP` and call `save_bundle()` on the result.
4. **Document** (~15 min): Write `metadata.yaml` (questions, expected conclusions,
   required evidence, forbidden behaviors).
5. **Review** (~15 min): Code review — is the fixture accurate? minimal? correct?

**Schema migrations:** When `InvestigationArtifact` gains new fields, re-run
step 3 on each fixture to regenerate `expected.json`. No migration script needed
until 10+ fixtures exist.

---

## Exit Criteria

- [ ] Step 0 complete: `_comparable()` extracted to `tests/helpers/artifact_assertions.py`
- [ ] 3–5 fixtures exist in `tests/fixtures/`, each with `data/`, `expected.json`,
      `metadata.yaml`
- [ ] Each fixture covers a distinct reasoning scenario (A–E above)
- [ ] `fixture_loader.py` implemented in `tests/helpers/`
- [ ] Replay tests in `tests/replay/` pass in CI
- [ ] Phase 4 (eval) is unblocked: `metadata.yaml` present with questions on all fixtures

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR | 9 issues found, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**VERDICT:** ENG CLEARED — ready to implement.
