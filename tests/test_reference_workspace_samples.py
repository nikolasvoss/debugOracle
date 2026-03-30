from __future__ import annotations

import json
import unittest
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from debugoracle.artifacts.models import (
    CURRENT_BUNDLE_SCHEMA_VERSION,
    InvestigationArtifact,
)
from debugoracle.cli import main as cli_main


STM32_WORKSPACES_ROOT = (
    Path(__file__).parent.parent
    / "examples"
    / "debugoracle-reference-workspaces"
    / "stm32"
)

# Each entry: (workspace_name, expected_stop_reason_or_none, has_halt_context)
WORKSPACE_SAMPLES = [
    ("hardfault", "signal-received", True),
    ("peripheral-miscfg", "breakpoint-hit", True),
    ("watchdog-timeout", None, False),
    ("healthy", "breakpoint-hit", True),
]


class ReferenceWorkspaceSampleTests(unittest.TestCase):
    """Validate that each workspace samples/snapshot.json is schema-valid and
    renders cleanly via the CLI. Catches silent regressions from schema evolution."""

    def _snapshot_path(self, workspace: str) -> Path:
        return STM32_WORKSPACES_ROOT / workspace / "samples" / "snapshot.json"

    def _run_report(self, snapshot_path: Path) -> tuple[int, str, str]:
        stdout_buf = StringIO()
        stderr_buf = StringIO()
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                cli_main(["report", "--snapshot-file", str(snapshot_path)])
            return (0, stdout_buf.getvalue(), stderr_buf.getvalue())
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            return (code, stdout_buf.getvalue(), stderr_buf.getvalue())

    def test_all_snapshots_exist(self):
        for ws, _, _ in WORKSPACE_SAMPLES:
            path = self._snapshot_path(ws)
            self.assertTrue(
                path.exists(),
                f"Missing snapshot: {path}",
            )

    def test_snapshots_are_valid_json(self):
        for ws, _, _ in WORKSPACE_SAMPLES:
            path = self._snapshot_path(ws)
            with self.subTest(workspace=ws):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self.assertIsInstance(data, dict)

    def test_snapshots_deserialize_via_from_dict(self):
        for ws, _, _ in WORKSPACE_SAMPLES:
            path = self._snapshot_path(ws)
            with self.subTest(workspace=ws):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                artifact = InvestigationArtifact.from_dict(data)
                self.assertIsInstance(artifact, InvestigationArtifact)
                self.assertEqual(artifact.schema_version, CURRENT_BUNDLE_SCHEMA_VERSION)

    def test_snapshots_have_correct_stop_reason(self):
        for ws, expected_stop_reason, _ in WORKSPACE_SAMPLES:
            path = self._snapshot_path(ws)
            with self.subTest(workspace=ws):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                artifact = InvestigationArtifact.from_dict(data)
                self.assertEqual(
                    artifact.stop_reason,
                    expected_stop_reason,
                    f"{ws}: expected stop_reason={expected_stop_reason!r}, got {artifact.stop_reason!r}",
                )

    def test_report_command_exits_zero(self):
        for ws, _, _ in WORKSPACE_SAMPLES:
            path = self._snapshot_path(ws)
            with self.subTest(workspace=ws):
                code, stdout, stderr = self._run_report(path)
                self.assertEqual(
                    code,
                    0,
                    f"{ws}: report exited {code}\nstdout: {stdout}\nstderr: {stderr}",
                )

    def test_report_output_contains_stop_reason_section(self):
        for ws, expected_stop_reason, _ in WORKSPACE_SAMPLES:
            path = self._snapshot_path(ws)
            with self.subTest(workspace=ws):
                code, stdout, _ = self._run_report(path)
                self.assertEqual(code, 0)
                if expected_stop_reason is not None:
                    self.assertIn(
                        expected_stop_reason,
                        stdout,
                        f"{ws}: expected '{expected_stop_reason}' in report output",
                    )

    def test_watchdog_snapshot_has_no_halt_context(self):
        """watchdog-timeout snapshot must have null stop_reason and empty live_state."""
        path = self._snapshot_path("watchdog-timeout")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        artifact = InvestigationArtifact.from_dict(data)
        self.assertIsNone(artifact.stop_reason)
        self.assertIsNone(artifact.pc)
        self.assertIsNone(artifact.lr)
        self.assertIsNone(artifact.sp)
        self.assertEqual(artifact.frames, [])

    def test_watchdog_snapshot_has_rtt_lines(self):
        """watchdog-timeout primary evidence is RTT — must have content."""
        path = self._snapshot_path("watchdog-timeout")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        artifact = InvestigationArtifact.from_dict(data)
        self.assertGreater(len(artifact.sources.rtt.lines), 0)
        # Last RTT line should reference the hang
        self.assertTrue(
            any(
                "hang" in line.lower() or "iwdg" in line.lower()
                for line in artifact.sources.rtt.lines
            ),
            "watchdog RTT should contain hang/IWDG reference",
        )

    def test_hardfault_snapshot_has_cfsr(self):
        """hardfault snapshot must have CFSR populated in registers."""
        path = self._snapshot_path("hardfault")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        artifact = InvestigationArtifact.from_dict(data)
        self.assertIn(
            "CFSR", artifact.registers, "hardfault snapshot must have CFSR register"
        )
        self.assertIn(
            "BFAR", artifact.registers, "hardfault snapshot must have BFAR register"
        )

    def test_peripheral_miscfg_snapshot_has_usart_brr(self):
        """peripheral-miscfg snapshot must have USART1_BRR in registers."""
        path = self._snapshot_path("peripheral-miscfg")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        artifact = InvestigationArtifact.from_dict(data)
        self.assertIn(
            "USART1_BRR",
            artifact.registers,
            "peripheral-miscfg snapshot must have USART1_BRR register",
        )
        self.assertEqual(
            artifact.registers["USART1_BRR"].upper(),
            "0X208D",
            "USART1_BRR should be 0x208D (9600 baud at 80MHz)",
        )

    def test_healthy_snapshot_has_variable_evidence(self):
        """healthy snapshot must have locals including gpio_test_pass_count."""
        path = self._snapshot_path("healthy")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        artifact = InvestigationArtifact.from_dict(data)
        local_names = [v.name for v in artifact.variable_evidence.locals]
        self.assertIn(
            "gpio_test_pass_count",
            local_names,
            "healthy snapshot must have gpio_test_pass_count in locals",
        )
