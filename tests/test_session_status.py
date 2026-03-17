from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from debugoracle.builder import build_bundle_from_files, save_bundle
from debugoracle.rtt import RttCaptureState, default_state_path
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
        self.assertFalse(status.rtt_capture.exists)

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

        self.assertEqual(status.health, "healthy")
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

    def test_collect_session_status_keeps_non_mi_noise_as_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            noisy_log = (
                "(gdb)\n"
                '@"Unable to match requested speed 500 kHz, using 480 kHz\\n"\n'
                "17+download,{section=\".text\",section-size=\"1\",total-size=\"1\"}\n"
                + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
            )
            (session_dir / "cortex-debug-shared-mi.log").write_text(noisy_log, encoding="utf-8")
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            bundle = build_bundle_from_files(str(session_dir / "cortex-debug-shared-mi.log"), str(session_dir / "session.rtt"))
            save_bundle(bundle, str(session_dir / "latest_snapshot.json"))

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertGreater(status.parse_warning_count, 0)

    def test_collect_session_status_treats_mi_parse_warnings_as_non_health_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            noisy_log = (
                (FIXTURES / "sample.mi").read_text(encoding="utf-8")
                + "\n"
                + "2*not-a-record\n"
            )
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                noisy_log,
                encoding="utf-8",
            )
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            bundle = build_bundle_from_files(
                str(session_dir / "cortex-debug-shared-mi.log"),
                str(session_dir / "session.rtt"),
            )
            save_bundle(bundle, str(session_dir / "latest_snapshot.json"))

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertTrue(any("unable to parse MI record" in message for message in status.parse_warnings))

    def test_collect_session_status_reads_rtt_capture_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            session_dir = Path(workspace) / ".dbgoracle"
            self._write_rtt_state(
                session_dir / "session.rtt",
                status="eof",
                bytes_captured=42,
                last_byte_at="2026-03-16T10:00:05+00:00",
            )

            session_status = collect_session_status(SessionConfig.from_workspace(workspace))

        self.assertEqual(session_status.health, "healthy")
        self.assertTrue(session_status.rtt_capture.exists)
        self.assertEqual(session_status.rtt_capture.status, "eof")
        self.assertEqual(session_status.rtt_capture.bytes_captured, 42)
        self.assertEqual(session_status.rtt_capture.host, "127.0.0.1")

    def test_collect_session_status_uses_custom_rtt_state_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            (Path(workspace) / "alt").mkdir()
            custom_state_path = Path(workspace) / "alt" / "rtt.state.json"
            self._write_rtt_state(
                Path(workspace) / ".dbgoracle" / "session.rtt",
                status="eof",
                bytes_captured=16,
                last_byte_at="2026-03-16T10:00:10+00:00",
                state_path=custom_state_path,
            )

            status = collect_session_status(
                SessionConfig.from_workspace(
                    workspace,
                    rtt_state_file=custom_state_path,
                )
            )

        self.assertTrue(status.rtt_capture.exists)
        self.assertEqual(status.rtt_capture.path, str(custom_state_path))
        self.assertEqual(status.rtt_capture.status, "eof")
        self.assertEqual(status.rtt_capture.bytes_captured, 16)

    def test_collect_session_status_surfaces_connected_but_empty_rtt_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            bundle = build_bundle_from_files(str(FIXTURES / "sample.mi"))
            save_bundle(bundle, str(session_dir / "latest_snapshot.json"))
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "session.rtt").write_text("", encoding="utf-8")
            self._write_rtt_state(session_dir / "session.rtt", status="connected", bytes_captured=0)

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertIn("RTT capture connected but no bytes were captured yet.", status.warnings)
        self.assertIn("RTT log file exists but is still empty.", status.warnings)

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

    def _write_rtt_state(
        self,
        target_path: Path,
        *,
        status: str,
        bytes_captured: int,
        last_byte_at: str | None = None,
        state_path: Path | None = None,
    ) -> None:
        state = RttCaptureState(
            source="openocd-rtt-tcp",
            host="127.0.0.1",
            port=60001,
            status=status,
            connected_at="2026-03-16T10:00:00+00:00",
            last_byte_at=last_byte_at,
            bytes_captured=bytes_captured,
            error=None,
        )
        target = default_state_path(target_path) if state_path is None else state_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(state.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
