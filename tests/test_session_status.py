from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from debugoracle.artifacts.repository import save_artifact
from debugoracle.builder import build_bundle_from_files
from debugoracle.rtt import RttCaptureState, default_state_path
from debugoracle.openocd import (
    DISCOVERY_MATCHED,
    DISCOVERY_NO_SESSION,
    OpenOcdCandidate,
    OpenOcdDiscoveryResult,
)
from debugoracle.session import SessionConfig, collect_session_status


FIXTURES = Path(__file__).parent / "fixtures"


class SessionStatusTests(unittest.TestCase):
    def test_collect_session_status_reports_healthy_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            status = collect_session_status(SessionConfig.from_workspace(workspace))

        self.assertEqual(status.health, "healthy")
        self.assertEqual(status.trust["verdict"], "safe")
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
        self.assertEqual(status.trust["verdict"], "unsafe")
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

    def test_collect_session_status_recommends_refresh_when_raw_evidence_is_newer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            session_dir = Path(workspace) / ".dbgoracle"
            now = datetime.now(timezone.utc)
            snapshot_time = (now - timedelta(hours=2)).timestamp()
            fresh_time = (now - timedelta(seconds=30)).timestamp()
            os.utime(
                session_dir / "latest_snapshot.json", (snapshot_time, snapshot_time)
            )
            os.utime(
                session_dir / "cortex-debug-shared-mi.log", (fresh_time, fresh_time)
            )
            os.utime(session_dir / "session.rtt", (fresh_time, fresh_time))

            status = collect_session_status(
                SessionConfig.from_workspace(workspace, stale_after_seconds=60)
            )

        self.assertEqual(status.action_state, "refresh_recommended")
        self.assertEqual(status.trust["verdict"], "unsafe")
        self.assertEqual(
            status.recommended_next_command, "dbgoracle fetch --workspace-root ."
        )
        self.assertIn(
            "raw evidence is newer than the snapshot", status.action_reason.lower()
        )

    def test_collect_session_status_surfaces_corrupt_snapshot_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            (session_dir / "latest_snapshot.json").write_text(
                "{ not json", encoding="utf-8"
            )
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
        self.assertEqual(status.trust["verdict"], "unsafe")
        self.assertIsNone(status.snapshot_id)
        self.assertEqual(status.parse_warning_count, 1)
        self.assertEqual(status.action_state, "capture_needed")
        self.assertEqual(
            status.recommended_next_command, "dbgoracle fetch --workspace-root ."
        )
        self.assertIn("Could not parse snapshot JSON", status.parse_warnings[0])

    def test_collect_session_status_keeps_optional_rtt_warning_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            bundle = build_bundle_from_files(str(FIXTURES / "sample.mi"))
            save_artifact(bundle, str(session_dir / "latest_snapshot.json"))
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
                '17+download,{section=".text",section-size="1",total-size="1"}\n'
                + (FIXTURES / "sample.mi").read_text(encoding="utf-8")
            )
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                noisy_log, encoding="utf-8"
            )
            (session_dir / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            bundle = build_bundle_from_files(
                str(session_dir / "cortex-debug-shared-mi.log"),
                str(session_dir / "session.rtt"),
            )
            save_artifact(bundle, str(session_dir / "latest_snapshot.json"))

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertGreater(status.parse_warning_count, 0)

    def test_collect_session_status_treats_mi_parse_warnings_as_non_health_issues(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            noisy_log = (
                (FIXTURES / "sample.mi").read_text(encoding="utf-8")
                + "\n"
                + '*stopped,reason="unterminated\n'
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
            save_artifact(bundle, str(session_dir / "latest_snapshot.json"))

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertTrue(
            any(
                "unable to parse MI record" in message
                for message in status.parse_warnings
            )
        )

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

            session_status = collect_session_status(
                SessionConfig.from_workspace(workspace)
            )

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

    def test_collect_session_status_surfaces_connected_but_empty_rtt_capture(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            bundle = build_bundle_from_files(str(FIXTURES / "sample.mi"))
            save_artifact(bundle, str(session_dir / "latest_snapshot.json"))
            (session_dir / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (session_dir / "session.rtt").write_text("", encoding="utf-8")
            self._write_rtt_state(
                session_dir / "session.rtt", status="connected", bytes_captured=0
            )

            status = collect_session_status(SessionConfig.from_workspace(tmpdir))

        self.assertEqual(status.health, "healthy")
        self.assertIn(
            "RTT capture connected but no bytes were captured yet.", status.warnings
        )
        self.assertIn("RTT log file exists but is still empty.", status.warnings)

    def test_collect_session_status_degrades_running_target_artifact_via_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / ".dbgoracle"
            session_dir.mkdir()
            bundle = build_bundle_from_files(
                str(FIXTURES / "sample.mi"),
                str(FIXTURES / "sample.rtt"),
            )
            bundle.live_state = {
                "backend": "demo",
                "target_state": "running",
                "warnings": [],
            }
            save_artifact(bundle, str(session_dir / "latest_snapshot.json"))
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
        self.assertIn("halted analysis is required", "\n".join(status.warnings).lower())
        self.assertIn("target state 'running'", "\n".join(status.warnings).lower())

    def test_collect_session_status_marks_attach_workspace_as_prepared_without_live_proof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            self._write_attach_workspace(workspace)
            with patch(
                "debugoracle.session.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                status = collect_session_status(SessionConfig.from_workspace(workspace))

        self.assertEqual(status.readiness.state, "prepared")
        self.assertEqual(
            status.readiness.launch_config_name, "DebugOracle: Attach STM32"
        )
        self.assertIn(
            "Start `DebugOracle: Attach STM32`", status.readiness.next_human_action
        )

    def test_collect_session_status_promotes_attach_workspace_to_live_on_multi_signal_proof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(self._prepare_workspace(tmpdir))
            self._write_attach_workspace(workspace)
            candidate = OpenOcdCandidate(
                pid=1234,
                argv=("openocd", "-c", "tcl_port 50001"),
                cwd=str(workspace),
                host="127.0.0.1",
                tcl_port=50001,
                gdb_port=None,
                telnet_port=None,
            )
            with patch(
                "debugoracle.session.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(
                    status=DISCOVERY_MATCHED, candidate=candidate
                ),
            ):
                status = collect_session_status(SessionConfig.from_workspace(workspace))

        self.assertEqual(status.readiness.state, "live")
        self.assertIn("multiple live runtime signals agree", status.readiness.reason)

    def test_collect_session_status_marks_attach_workspace_degraded_when_signals_are_ambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(self._prepare_workspace(tmpdir))
            self._write_attach_workspace(workspace)
            with patch(
                "debugoracle.session.discover_workspace_openocd_session",
                return_value=OpenOcdDiscoveryResult(status=DISCOVERY_NO_SESSION),
            ):
                status = collect_session_status(SessionConfig.from_workspace(workspace))

        self.assertEqual(status.readiness.state, "degraded")
        self.assertIn("not trusted as live yet", status.readiness.reason)
        self.assertIn(
            "Restart `DebugOracle: Attach STM32`", status.readiness.next_human_action
        )

    def _prepare_workspace(self, tmpdir: str) -> str:
        workspace = Path(tmpdir)
        session_dir = workspace / ".dbgoracle"
        session_dir.mkdir()
        bundle = build_bundle_from_files(
            str(FIXTURES / "sample.mi"),
            str(FIXTURES / "sample.rtt"),
        )
        save_artifact(bundle, str(session_dir / "latest_snapshot.json"))
        (session_dir / "cortex-debug-shared-mi.log").write_text(
            (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (session_dir / "session.rtt").write_text(
            (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return str(workspace)

    def _write_attach_workspace(self, workspace: Path) -> None:
        vscode_dir = workspace / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        (vscode_dir / "settings.json").write_text(
            json.dumps(
                {
                    "debugoracle.workspaceSetupMode": "attach",
                    "debugoracle.launchConfigName": "DebugOracle: Attach STM32",
                    "debugoracle.launchConfigRole": "golden-path-attach",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (vscode_dir / "launch.json").write_text(
            json.dumps(
                {
                    "version": "0.2.0",
                    "configurations": [
                        {
                            "name": "DebugOracle: Attach STM32",
                            "type": "cortex-debug",
                            "request": "launch",
                            "debugoracleRole": "golden-path-attach",
                            "preLaunchTask": "DebugOracle: Prelaunch",
                            "postDebugTask": "DebugOracle: Stop RTT run",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (vscode_dir / "tasks.json").write_text(
            json.dumps(
                {
                    "version": "2.0.0",
                    "tasks": [
                        {"label": "DebugOracle: Prelaunch"},
                        {"label": "DebugOracle: Stop RTT run"},
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

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

    def test_render_session_status_surfaces_action_first_summary(self) -> None:
        from debugoracle.renderers.status import render_session_status

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = self._prepare_workspace(tmpdir)
            status = collect_session_status(SessionConfig.from_workspace(workspace))

        rendered = render_session_status(status)
        self.assertIn("Current State:", rendered)
        self.assertIn("Evidence Availability:", rendered)
        self.assertIn("Next Useful Command:", rendered)
        self.assertIn("- Snapshot: available", rendered)


if __name__ == "__main__":
    unittest.main()
