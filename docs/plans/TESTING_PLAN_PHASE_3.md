# DebugOracle — Replay Fixtures Plan

**Status:** Complete (replay fixtures track closed)
**Track:** Replay fixtures
**Source plan:** Legacy `docs/plans/testing_rework.md §5, §8.6` (file removed; this doc is canonical)
**Reviewed by:** `/plan-eng-review` 2026-03-27
**Implementation updated:** 2026-04-08

---

## Context

This track builds deterministic replay fixtures from real debug sessions to
protect against regressions in real-world behavior.

Implemented target:
- 3 fixture bundles in `tests/fixtures/`
- replay regression tests in `tests/replay/`
- shared test helpers in `tests/helpers/`

Naming rule used in implementation:
- Scenario-based names only (`signal_received_stop`, `missing_stop_evidence`,
  `conflicting_stop_events`)
- No milestone/phase-prefixed fixture names

---

## Implemented Architecture

```
Real debug session data
        │
        ▼
Minimized fixture bundle
tests/fixtures/{scenario}/
  ├── data/gdb.log
  ├── data/rtt.log
  ├── metadata.yaml
  └── expected.json
        │
        ▼
tests/replay/test_replay_fixtures.py
  - load_fixture_data()
  - build_bundle_from_text(..., export_raw=True)
  - load_artifact(expected.json)
  - comparable(...) equality assertion
```

Serialization APIs used in implementation:
- `debugoracle.artifacts.repository.save_artifact`
- `debugoracle.artifacts.repository.load_artifact`

---

## Implemented Fixtures

1. `tests/fixtures/signal_received_stop/`
   Scenario: real MI stop event with `signal-received` and stack evidence.
2. `tests/fixtures/missing_stop_evidence/`
   Scenario: RTT-only input; missing MI evidence must keep stop fields unknown/None.
3. `tests/fixtures/conflicting_stop_events/`
   Scenario: two conflicting stop reasons; selected value must be one observed value.

Each fixture includes:
- `data/gdb.log`
- `data/rtt.log`
- `metadata.yaml`
- `expected.json`

---

## Test Implementation

Implemented files:
- `tests/replay/test_replay_fixtures.py`
- `tests/helpers/fixture_loader.py`
- `tests/helpers/artifact_assertions.py`

Contract test reuse:
- `tests/contracts/test_core_invariants.py` now imports shared `comparable()`.

Comparison behavior:
- `captured_at` and `snapshot_id` are excluded.
- `sources.gdb.events` is excluded due to known load-time payload coercion.

---

## Exit Criteria

- [x] Shared artifact comparison helper extracted to `tests/helpers/artifact_assertions.py`
- [x] `fixture_loader.py` implemented in `tests/helpers/`
- [x] 3 fixture bundles exist with `data/`, `metadata.yaml`, `expected.json`
- [x] Distinct reasoning scenarios covered by fixtures
- [x] Replay tests implemented and passing locally
- [x] Metadata present for all fixtures (eval-input-ready)

Result:
- Replay fixtures track is complete and unblocks question-centric eval work.

---

## Validation Record

Executed locally:
- `python -m unittest discover -s tests/replay -p 'test_*.py' -v` (pass)
- `python -m unittest tests.contracts.test_core_invariants -v` (pass)

Environment note:
- `./.venv/bin/pre-commit run --all-files` executed successfully
  (ruff, pyright, pytest-fast, coverage, bandit all passing).

---

## Open Questions

- No blocking open questions remain for replay fixtures.
