"""Contract tests for DebugOracle core invariants.

Each test class corresponds to one invariant from docs/specs/testing-requirements.md.
Failures here indicate a core invariant was broken, not an implementation detail.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from debugoracle.artifacts.models import (
    EvidenceAnswer,
    InvestigationArtifact,
)
from debugoracle.builder import build_bundle_from_text
from debugoracle.artifacts.bundle import load_bundle, save_bundle

FIXED_TIMESTAMP = "2024-01-01T00:00:00Z"

# Minimal MI log that contains a stop event with a frame
MINIMAL_MI = """\
*stopped,reason="breakpoint-hit",frame={addr="0x08000100",func="main"},thread-id="1",stopped-threads="all"
"""


class DeterminismContractTests(unittest.TestCase):
    """Invariant 1: Same inputs produce same outputs."""

    def _build(self, mi: str = "", rtt: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi, rtt)

    def _comparable(self, artifact: InvestigationArtifact) -> dict:
        d = dataclasses.asdict(artifact)
        d.pop("captured_at", None)
        d.pop("snapshot_id", None)
        return d

    def test_empty_inputs_produce_equal_artifacts(self) -> None:
        a = self._build()
        b = self._build()
        self.assertEqual(self._comparable(a), self._comparable(b))

    def test_mi_inputs_produce_equal_artifacts(self) -> None:
        a = self._build(mi=MINIMAL_MI)
        b = self._build(mi=MINIMAL_MI)
        self.assertEqual(self._comparable(a), self._comparable(b))

    def test_snapshot_id_is_deterministic(self) -> None:
        a = self._build(mi=MINIMAL_MI, rtt="hello\nworld\n")
        b = self._build(mi=MINIMAL_MI, rtt="hello\nworld\n")
        self.assertEqual(a.snapshot_id, b.snapshot_id)

    def test_captured_at_is_string(self) -> None:
        artifact = self._build()
        self.assertIsInstance(artifact.captured_at, str)

    def test_schema_version_is_current(self) -> None:
        from debugoracle.artifacts.models import CURRENT_BUNDLE_SCHEMA_VERSION

        artifact = self._build()
        self.assertEqual(artifact.schema_version, CURRENT_BUNDLE_SCHEMA_VERSION)


class EvidenceFirstContractTests(unittest.TestCase):
    """Invariant 2: No inferred or guessed state — everything traces to a source."""

    def _build(self, mi: str = "", rtt: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi, rtt)

    def test_empty_mi_produces_none_stop_reason(self) -> None:
        artifact = self._build(mi="")
        self.assertIsNone(artifact.stop_reason)

    def test_empty_mi_produces_none_pc(self) -> None:
        artifact = self._build(mi="")
        self.assertIsNone(artifact.pc)

    def test_empty_mi_produces_none_lr(self) -> None:
        artifact = self._build(mi="")
        self.assertIsNone(artifact.lr)

    def test_empty_mi_produces_none_sp(self) -> None:
        artifact = self._build(mi="")
        self.assertIsNone(artifact.sp)

    def test_empty_mi_produces_no_variable_entries(self) -> None:
        artifact = self._build(mi="")
        self.assertEqual(artifact.variable_evidence.count(), 0)

    def test_variable_entries_have_origin_set(self) -> None:
        mi = MINIMAL_MI + '~"[locals] system_state=READY"\n'
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            artifact = build_bundle_from_text(mi)
        for entry in artifact.variable_evidence.all_entries():
            self.assertIsInstance(entry.origin, str)
            self.assertNotEqual(
                entry.origin, "", f"VariableEntry '{entry.name}' has empty origin"
            )

    def test_mi_stop_event_sets_stop_reason(self) -> None:
        artifact = self._build(mi=MINIMAL_MI)
        self.assertEqual(artifact.stop_reason, "breakpoint-hit")


class ReadOnlyContractTests(unittest.TestCase):
    """Invariant 3: Build pipeline does not mutate the target system."""

    def test_build_pipeline_does_not_invoke_shell(self) -> None:
        with (
            patch("subprocess.run") as mock_run,
            patch("subprocess.Popen") as mock_popen,
            patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP),
        ):
            build_bundle_from_text(MINIMAL_MI, "")
        mock_run.assert_not_called()
        mock_popen.assert_not_called()

    def test_build_pipeline_does_not_call_os_system(self) -> None:
        with (
            patch("os.system") as mock_os_system,
            patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP),
        ):
            build_bundle_from_text(MINIMAL_MI, "")
        mock_os_system.assert_not_called()


class ReproducibleContractTests(unittest.TestCase):
    """Invariant 4: Artifacts allow offline reconstruction of reasoning."""

    def _build(self, mi: str = "", rtt: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi, rtt, export_raw=True)

    def test_artifact_with_gdb_source_embeds_raw_text(self) -> None:
        artifact = self._build(mi=MINIMAL_MI)
        self.assertTrue(artifact.sources.gdb.embedded)
        self.assertIsNotNone(artifact.sources.gdb.raw_text)
        self.assertIn("breakpoint-hit", artifact.sources.gdb.raw_text or "")

    def test_artifact_with_rtt_source_embeds_raw_text(self) -> None:
        artifact = self._build(mi=MINIMAL_MI, rtt="hello RTT\n")
        self.assertTrue(artifact.sources.rtt.embedded)
        self.assertIsNotNone(artifact.sources.rtt.raw_text)

    def test_save_load_round_trip_produces_equal_artifact(self) -> None:
        artifact = self._build(mi=MINIMAL_MI, rtt="hello\n")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "artifact.json")
            save_bundle(artifact, path)
            loaded = load_bundle(path)
        self.assertEqual(artifact.stop_reason, loaded.stop_reason)
        self.assertEqual(artifact.pc, loaded.pc)
        self.assertEqual(artifact.schema_version, loaded.schema_version)
        self.assertEqual(artifact.snapshot_id, loaded.snapshot_id)


class ProvenanceContractTests(unittest.TestCase):
    """Invariant 5: Every piece of data is traceable to its origin."""

    def _build(self, mi: str = "", rtt: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi, rtt)

    def test_sources_report_embedded_false_for_empty_inputs(self) -> None:
        artifact = self._build(mi="", rtt="")
        self.assertFalse(artifact.sources.gdb.embedded)
        self.assertFalse(artifact.sources.rtt.embedded)

    def test_sources_report_embedded_true_when_mi_present(self) -> None:
        artifact = self._build(mi=MINIMAL_MI)
        self.assertTrue(artifact.sources.gdb.embedded)

    def test_sources_report_embedded_true_when_rtt_present(self) -> None:
        artifact = self._build(mi=MINIMAL_MI, rtt="rtt line\n")
        self.assertTrue(artifact.sources.rtt.embedded)


class EvidenceAnswerContractTests(unittest.TestCase):
    """Contract tests for the EvidenceAnswer type (docs/specs/testing-contracts.md)."""

    def test_evidence_answer_is_frozen_dataclass(self) -> None:
        answer = EvidenceAnswer(question="q", conclusion="c", confidence="high")
        with self.assertRaises((dataclasses.FrozenInstanceError, AttributeError)):
            answer.conclusion = "mutated"  # type: ignore[misc]

    def test_evidence_answer_unknown_convention(self) -> None:
        answer = EvidenceAnswer(
            question="What caused the fault?",
            conclusion="unknown",
            confidence="unknown",
            evidence_sources=[],
            conflicts=[],
        )
        self.assertEqual(answer.conclusion, "unknown")
        self.assertEqual(answer.confidence, "unknown")
        self.assertEqual(answer.evidence_sources, [])

    def test_evidence_answer_with_sources_and_conflicts(self) -> None:
        answer = EvidenceAnswer(
            question="Is the stack corrupted?",
            conclusion="yes",
            confidence="high",
            evidence_sources=["gdb_halt_snapshot"],
            conflicts=[],
            provenance={"conclusion": "gdb_halt_snapshot:frames"},
        )
        self.assertEqual(answer.confidence, "high")
        self.assertIn("gdb_halt_snapshot", answer.evidence_sources)
        self.assertIn("conclusion", answer.provenance)

    def test_evidence_answer_exports_via_asdict(self) -> None:
        answer = EvidenceAnswer(
            question="q",
            conclusion="unknown",
            confidence="unknown",
        )
        d = dataclasses.asdict(answer)
        self.assertIn("question", d)
        self.assertIn("conclusion", d)
        self.assertIn("confidence", d)
        self.assertIn("evidence_sources", d)
        self.assertIn("conflicts", d)
        self.assertIn("provenance", d)


class UncertaintyContractTests(unittest.TestCase):
    """Invariant: Insufficient or conflicting evidence is surfaced, never fabricated.

    Corresponds to testing-requirements.md §Uncertainty Handling Requirements.
    """

    def _build(self, mi: str = "", rtt: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi, rtt)

    def test_malformed_mi_does_not_fabricate_stop_reason(self) -> None:
        artifact = self._build(mi="THIS IS NOT VALID MI OUTPUT\n")
        self.assertIsNone(
            artifact.stop_reason,
            "unrecognised MI must not produce a fabricated stop_reason",
        )

    def test_conflicting_stop_events_produce_one_of_the_observed_values(self) -> None:
        # Two *stopped events with different reasons — parser must pick one, not invent a third.
        mi = (
            MINIMAL_MI
            + '*stopped,reason="watchpoint-trigger",'
            'frame={addr="0x0"},thread-id="1",stopped-threads="all"\n'
        )
        artifact = self._build(mi=mi)
        self.assertIn(
            artifact.stop_reason,
            {"breakpoint-hit", "watchpoint-trigger"},
            "stop_reason must be one of the two observed values, not fabricated",
        )


class ArtifactImmutabilityContractTests(unittest.TestCase):
    """Invariant: Artifacts must not be mutated by the render path.

    Corresponds to testing_rework.md §4.6 and testing-requirements.md §Read-Only by Default.
    """

    def test_render_report_does_not_mutate_artifact(self) -> None:
        from debugoracle.renderers.report import render_report

        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            artifact = build_bundle_from_text(MINIMAL_MI, "")
        before = dataclasses.asdict(artifact)
        render_report(artifact)
        after = dataclasses.asdict(artifact)
        self.assertEqual(before, after, "render_report must not mutate the artifact in-place")


class RoundTripContractTests(unittest.TestCase):
    """Invariant: Core artifact fields survive a save → load round-trip intact.

    Extends ReproducibleContractTests which only checked 3 fields.
    Corresponds to REQ-REPR-002.

    Note: session_events[].payload is excluded — _as_str_dict() stringifies nested
    values (ints, dicts) on load, which is a known serialisation limitation tracked
    separately.  All other fields must survive the round-trip unchanged.
    """

    def _build(self, mi: str = "", rtt: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi, rtt, export_raw=True)

    def _strip_session_events(self, d: dict) -> dict:
        """Remove session_events from an asdict() snapshot for comparison."""
        d = dict(d)
        d.pop("session_events", None)
        sources = dict(d.get("sources", {}))
        if "gdb" in sources:
            gdb = dict(sources["gdb"])
            gdb.pop("events", None)
            sources["gdb"] = gdb
        d["sources"] = sources
        return d

    def test_core_fields_survive_round_trip(self) -> None:
        artifact = self._build(mi=MINIMAL_MI, rtt="hello\n")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "artifact.json")
            save_bundle(artifact, path)
            loaded = load_bundle(path)
        orig = self._strip_session_events(dataclasses.asdict(artifact))
        restored = self._strip_session_events(dataclasses.asdict(loaded))
        self.assertEqual(orig, restored)


class ProvenancePopulatedContractTests(unittest.TestCase):
    """Invariant: provenance dict is non-empty when MI sources are present.

    Corresponds to REQ-PROV-003 and testing-requirements.md §Explicit Provenance.
    """

    def _build(self, mi: str = "") -> InvestigationArtifact:
        with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
            return build_bundle_from_text(mi)

    def test_provenance_non_empty_when_gdb_source_present(self) -> None:
        artifact = self._build(mi=MINIMAL_MI)
        self.assertGreater(
            len(artifact.provenance),
            0,
            "provenance must be non-empty when MI source is present",
        )

    def test_provenance_includes_event_count(self) -> None:
        artifact = self._build(mi=MINIMAL_MI)
        self.assertIn(
            "gdb_event_count",
            artifact.provenance,
            "provenance must record the number of GDB events parsed",
        )


if __name__ == "__main__":
    unittest.main()
