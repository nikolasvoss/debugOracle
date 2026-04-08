from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from debugoracle.artifacts.repository import load_artifact
from debugoracle.builder import build_bundle_from_text
from tests.helpers.artifact_assertions import comparable
from tests.helpers.fixture_loader import load_fixture_data

FIXED_TIMESTAMP = "2024-01-01T00:00:00Z"
FIXTURE_ROOT = Path("tests/fixtures")


def discover_fixture_dirs() -> list[Path]:
    fixture_dirs: list[Path] = []
    for path in sorted(FIXTURE_ROOT.iterdir()):
        if not path.is_dir():
            continue
        if not (path / "data" / "gdb.log").is_file():
            continue
        if not (path / "data" / "rtt.log").is_file():
            continue
        if not (path / "metadata.yaml").is_file():
            continue
        if not (path / "expected.json").is_file():
            continue
        fixture_dirs.append(path)
    return fixture_dirs


class ReplayFixtureTests(unittest.TestCase):
    def test_fixture_bundles_include_required_files(self) -> None:
        fixture_dirs = discover_fixture_dirs()
        self.assertGreater(len(fixture_dirs), 0)
        for fixture_dir in fixture_dirs:
            with self.subTest(fixture=fixture_dir.name):
                self.assertTrue((fixture_dir / "data" / "gdb.log").exists())
                self.assertTrue((fixture_dir / "data" / "rtt.log").exists())
                self.assertTrue((fixture_dir / "metadata.yaml").exists())
                self.assertTrue((fixture_dir / "expected.json").exists())

    def test_loader_returns_raw_inputs_and_metadata(self) -> None:
        fixture_dir = FIXTURE_ROOT / "signal_received_stop"
        mi_text, rtt_text, metadata = load_fixture_data(fixture_dir)
        self.assertIn("*stopped", mi_text)
        self.assertIsInstance(rtt_text, str)
        self.assertEqual(metadata["name"], "signal_received_stop")
        self.assertIn("questions", metadata)

    def test_replay_artifacts_match_expected(self) -> None:
        for fixture_dir in discover_fixture_dirs():
            with self.subTest(fixture=fixture_dir.name):
                mi_text, rtt_text, _ = load_fixture_data(fixture_dir)
                with patch("debugoracle.builder.utc_now", return_value=FIXED_TIMESTAMP):
                    rebuilt = build_bundle_from_text(
                        gdb_text=mi_text,
                        rtt_text=rtt_text,
                        export_raw=True,
                    )
                expected = load_artifact(str(fixture_dir / "expected.json"))
                self.assertEqual(
                    comparable(rebuilt, exclude_gdb_events=True),
                    comparable(expected, exclude_gdb_events=True),
                )


if __name__ == "__main__":
    unittest.main()
