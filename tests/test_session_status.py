from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.session import SessionConfig, collect_session_status


FIXTURES = Path(__file__).parent / "fixtures"


class SessionStatusTests(unittest.TestCase):
    def test_collect_session_status_reports_healthy_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            status = collect_session_status(SessionConfig.from_workspace(workspace))

        self.assertEqual(status.health, "healthy")
        self.assertTrue(status.snapshot.exists)
        self.assertTrue(status.gdb_mi.exists)
        self.assertTrue(status.rtt.exists)
        self.assertEqual(status.parse_warning_count, 0)
        self.assertTrue((status.snapshot_id or "").startswith("snap-"))

    def test_collect_session_status_handles_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "degraded")
        self.assertFalse(status.snapshot.exists)
        self.assertFalse(status.gdb_mi.exists)
        self.assertFalse(status.rtt.exists)
        self.assertIn("No DebugOracle artifacts were found", "\n".join(status.warnings))

    def test_collect_session_status_marks_old_files_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            session_dir = Path(workspace) / ".dbgoracle"
            old_time = datetime.now(timezone.utc) - timedelta(hours=2)
            timestamp = old_time.timestamp()
            for path in session_dir.iterdir():
                os.utime(path, (timestamp, timestamp))

            status = collect_session_status(
                SessionConfig.from_workspace(workspace, stale_after_seconds=60)
            )

        self.assertEqual(status.health, "degraded")
        self.assertTrue(status.snapshot.stale)
        self.assertTrue(status.gdb_mi.stale)
        self.assertTrue(status.rtt.stale)
        self.assertIn("Snapshot file is stale", "\n".join(status.warnings))

    def test_collect_session_status_surfaces_corrupt_snapshot_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "latest_snapshot.json").write_text("{ not json", encoding="utf-8")
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "degraded")
        self.assertEqual(status.snapshot_id, "invalid-snapshot")
        self.assertEqual(status.parse_warning_count, 1)
        self.assertIn("Could not parse snapshot JSON", status.parse_warnings[0])

    def test_collect_session_status_keeps_optional_rtt_warning_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            bundle = build_bundle_from_files(str(FIXTURES / "sample.mi"))
            save_bundle(bundle, str(session_dir / "latest_snapshot.json"))
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertEqual(status.parse_warning_count, 1)
        self.assertIn("No RTT lines were available", status.parse_warnings[0])
        self.assertIn("RTT file not found", "\n".join(status.warnings))

    def _prepare_workspace(self, tmpdir: str) -> str:
        workspace = Path(tmpdir)
        session_dir = workspace / ".dbgoracle"
        session_dir.mkdir()
        bundle = build_bundle_from_files(
            str(FIXTURES / "sample.mi"),
            str(FIXTURES / "sample.rtt"),
        )
        save_bundle(bundle, str(session_dir / "latest_snapshot.json"))
        (session_dir / "cortex-debug-shared-mi.log").write_text(
            (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (session_dir / "session.rtt").write_text(
            (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return str(workspace)


if __name__ == "__main__":
    unittest.main()
