# DebugOracle — Testing Plan Phase 5: Adversarial & Metamorphic Tests

**Status:** Not started
**Phase:** 5 (Adversarial & Metamorphic Tests)
**Source plan:** Legacy `docs/plans/testing_rework.md §7` (file removed; phased docs are canonical)
**Reviewed by:** `/plan-eng-review` 2026-03-27
**Gate:** Phase 3 fixtures must exist (raw data + expected.json)

---

## Context

Phase 4 validates agent quality on realistic inputs. Phase 5 validates robustness
and trustworthiness via standard pytest tests — the properties that matter most
in agentic coding environments where "looks plausible" failures are dangerous.

Target:
- 3–5 metamorphic tests in `tests/metamorphic/`
- 3–5 adversarial tests in `tests/adversarial/`

Scale after the initial set is stable, not before.

---

## Architecture

```
tests/fixtures/{name}/data/gdb.log
tests/fixtures/{name}/data/rtt.log
        │
        ├─── FixtureTransformer ──→ transformed_mi_text / transformed_rtt_text
        │         │
        │   (tests/helpers/fixture_transformers.py)
        │   Operates on raw text — line/section level, not field-path surgery
        │
        ▼
build_bundle_from_text(transformed_mi, transformed_rtt)
        │
        ▼
InvestigationArtifact (deterministic, patched timestamp)
        │
        ▼
Oracle assertion (per-transformation contract)
        comparing: artifact fields, stop_reason, parse_warnings
```

**Note:** Phase 5 tests assert directly on `InvestigationArtifact` fields, NOT
on `EvidenceAnswer`. The eval (Phase 4) tests whether an agent answers correctly;
Phase 5 tests whether the *artifact* degrades correctly under adversarial inputs.

---

## Transformer Design: Line/Section Level

Transformers operate at **raw text level** — appending, deleting, or truncating
lines. No field-path surgery on MI format (which would require reverse-engineering
the MI serializer).

### `MetamorphicTransformer`

```python
class MetamorphicTransformer:
    @staticmethod
    def add_irrelevant_noise(raw_rtt: str, n_lines: int = 20) -> str:
        """Append N unrelated RTT lines that contain no evidence."""
        noise = "\n".join(f"[noise] unrelated log line {i}" for i in range(n_lines))
        return raw_rtt + "\n" + noise

    @staticmethod
    def reorder_non_semantic_records(raw_mi: str) -> str:
        """Shuffle lines that don't affect parse order (e.g. ^done lines)."""
        lines = raw_mi.splitlines(keepends=True)
        # Only shuffle non-stop-event lines to avoid changing stop semantics
        stop_lines = [l for l in lines if l.startswith("*stopped")]
        other_lines = [l for l in lines if not l.startswith("*stopped")]
        import random
        random.shuffle(other_lines)
        return "".join(other_lines + stop_lines)

    @staticmethod
    def duplicate_evidence_lines(raw_mi: str) -> str:
        """Duplicate every non-stop-event MI line."""
        result = []
        for line in raw_mi.splitlines(keepends=True):
            result.append(line)
            if not line.startswith("*stopped"):
                result.append(line)  # duplicate
        return "".join(result)

    @staticmethod
    def remove_section(raw_mi: str, section_prefix: str) -> str:
        """Remove all MI lines starting with the given prefix."""
        return "\n".join(
            line for line in raw_mi.splitlines()
            if not line.startswith(section_prefix)
        ) + "\n"
```

### `AdversarialTransformer`

```python
class AdversarialTransformer:
    @staticmethod
    def inject_conflicting_stop(raw_mi: str, new_reason: str) -> str:
        """Append a second stop event with a different reason at the end."""
        conflict_line = (
            f'*stopped,reason="{new_reason}",'
            f'frame={{addr="0xDEAD",func="unknown"}},thread-id="1"\n'
        )
        return raw_mi + conflict_line

    @staticmethod
    def add_misleading_label(raw_mi: str, label: str, value: str) -> str:
        """Append a ^done line with a signal name that implies something the data doesn't support."""
        misleading = f'^done,{label}="{value}"\n'
        return raw_mi + misleading

    @staticmethod
    def truncate(raw_mi: str, at_fraction: float = 0.5) -> str:
        """Truncate MI text at a given fraction of its length."""
        cut = int(len(raw_mi) * at_fraction)
        return raw_mi[:cut]

    @staticmethod
    def remove_rtt(raw_rtt: str) -> str:
        """Remove all RTT content (simulate missing RTT capture)."""
        return ""
```

All transformers produce strings. Callers pass the result to
`build_bundle_from_text()` — no separate validation step needed.

---

## Part 1 — Metamorphic Tests

### Oracle Table

| Transformation | Oracle | Assertion |
|---|---|---|
| `add_irrelevant_noise` | stop_reason preserved | `assert t.stop_reason == orig.stop_reason` |
| `reorder_non_semantic_records` | artifact semantically identical | `assert comparable(t) == comparable(orig)` |
| `duplicate_evidence_lines` | artifact unchanged | `assert comparable(t) == comparable(orig)` |
| `remove_section(stop prefix)` | stop_reason becomes None | `assert t.stop_reason is None` |

### Initial Tests (3–5)

**MM-01: Noise does not affect stop_reason**
- Fixture: `spi_mode_mismatch` data
- Transform: `add_irrelevant_noise(rtt, n_lines=50)`
- Oracle: `transformed.stop_reason == original.stop_reason`
- Why: Irrelevant RTT noise must not corrupt parsed GDB MI fields

**MM-02: Log record reordering does not change artifact**
- Fixture: any fixture with non-trivial MI
- Transform: `reorder_non_semantic_records(mi)` (shuffles non-stop lines)
- Oracle: `comparable(transformed) == comparable(original)`
- Why: Conclusion must not depend on incidental record ordering

**MM-03: Duplicate MI lines produce same artifact**
- Fixture: `spi_mode_match` data
- Transform: `duplicate_evidence_lines(mi)`
- Oracle: `comparable(transformed) == comparable(original)`
- Why: Duplicates are noise, not new evidence

**MM-04: Removing non-stop MI sections degrades gracefully**
- Fixture: `spi_mode_mismatch` (has variable evidence)
- Transform: `remove_section(mi, "^done,variables")`
- Oracle: artifact has empty variable list, stop_reason still set
- Why: Missing evidence class must degrade partially, not crash

**MM-05: Stop section removal produces None stop_reason**
- Fixture: any fixture
- Transform: `remove_section(mi, "*stopped")`
- Oracle: `transformed.stop_reason is None`
- Why: When stop evidence is gone, system must not fabricate a stop reason

---

## Part 2 — Adversarial Tests

### Oracle Table

| Transformation | Oracle | Assertion |
|---|---|---|
| `inject_conflicting_stop` | second stop captured; parse_warnings non-empty OR first wins | `assert t.stop_reason in {original_reason, new_reason}` (no fabricated third) |
| `add_misleading_label` | labels don't change stop_reason | `assert t.stop_reason == orig.stop_reason` |
| `truncate(0.5)` | no crash; stop_reason is None if stop line was truncated | `assert t.stop_reason is None or t.stop_reason == orig.stop_reason` |
| `remove_rtt` | artifact still builds; RTT source is empty | `assert t.gdb_source.embedded == orig_embedded and t.rtt_source.embedded == False` |

### Initial Tests (3–5)

**ADV-01: Conflicting stop events produce known value, not a fabricated third**
- Fixture: `spi_mode_mismatch` (original reason: `breakpoint-hit`)
- Transform: `inject_conflicting_stop(mi, "watchpoint-trigger")`
- Oracle: `transformed.stop_reason in {"breakpoint-hit", "watchpoint-trigger"}`
- Why: System picks one documented value; never invents a synthetic third

**ADV-02: Misleading signal labels don't change stop_reason**
- Fixture: any fixture with a stop event
- Transform: `add_misleading_label(mi, "signal_name", "SPI1_CONFIGURED_OK")`
- Oracle: `transformed.stop_reason == original.stop_reason`
- Why: Label metadata must not override evidence

**ADV-03: Truncated MI produces known state, not crash**
- Fixture: any fixture with non-trivial MI
- Transform: `truncate(mi, 0.5)` (cut at midpoint)
- Oracle: `build_bundle_from_text()` does not raise; `stop_reason` is None or
  matches original (depending on where the cut falls)
- Why: Corrupted/partial captures must degrade, not crash

**ADV-04: Missing RTT is handled gracefully**
- Fixture: `noisy_session` (which has significant RTT content)
- Transform: `remove_rtt(rtt)`
- Oracle: `transformed.rtt_source.embedded == False`; no crash; GDB source unchanged
- Why: Missing RTT is a realistic scenario (RTT capture failed)

**ADV-05: All stop event sections removed → stop_reason is None**
- Fixture: `spi_mode_match`
- Transform: `remove_section(mi, "*stopped")`
- Oracle: `transformed.stop_reason is None`; no fabrication
- Why: Strongest form of evidence removal — system must return explicit unknown state

---

## Coverage Matrix

```
Fixture Family     | inject_conflict | remove_section | truncate | add_label | remove_rtt
───────────────────┼─────────────────┼────────────────┼──────────┼───────────┼────────────
spi_mode_match     | ADV-01 ✓        | MM-05 ✓        | ADV-03 ✓ | ADV-02 ✓  | —
spi_mode_mismatch  | —               | MM-04 ✓        | —        | —         | —
missing_evidence   | —               | — (already)    | —        | —         | —
conflicting_src    | ✓               | —              | —        | —         | —
noisy_session      | —               | —              | —        | —         | ADV-04 ✓
```

Goal: Every fixture family covered under at least 3–4 adversarial/metamorphic
conditions before scaling fixture count.

---

## Test File Layout

```
tests/metamorphic/
  test_noise_invariance.py         # MM-01
  test_reorder_invariance.py       # MM-02, MM-03
  test_evidence_removal.py         # MM-04, MM-05

tests/adversarial/
  test_conflict_handling.py        # ADV-01
  test_misleading_inputs.py        # ADV-02
  test_corrupt_input.py            # ADV-03
  test_missing_sources.py          # ADV-04, ADV-05

tests/helpers/
  fixture_transformers.py          # MetamorphicTransformer + AdversarialTransformer
```

---

## Exit Criteria

- [ ] `fixture_transformers.py` implemented with both transformer classes
- [ ] 3–5 metamorphic tests in `tests/metamorphic/`, each with documented oracle
- [ ] 3–5 adversarial tests in `tests/adversarial/`, each with documented oracle
- [ ] All tests assert on `InvestigationArtifact` fields (not `EvidenceAnswer`, not text)
- [ ] Coverage matrix updated to reflect initial coverage
- [ ] All tests are standard pytest (no API key required, run in default CI)
- [ ] No transformer uses field-path surgery on MI text — all are line/section level

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR | 9 issues found, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**VERDICT:** ENG CLEARED — ready to implement.
