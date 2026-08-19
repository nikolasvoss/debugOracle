from __future__ import annotations

import json
import shutil
import tempfile
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
PERIPHERAL_DEMO_ROOT = STM32_WORKSPACES_ROOT / "peripheral-miscfg"

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

    def test_peripheral_miscfg_snapshot_has_clock_mismatch_evidence(self):
        """The demo fixture must contain both sides of the clock mismatch."""
        path = self._snapshot_path("peripheral-miscfg")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        artifact = InvestigationArtifact.from_dict(data)
        self.assertEqual(artifact.registers["RCC_CCIPR"].upper(), "0X00000002")
        self.assertEqual(artifact.registers["USART1_BRR"].upper(), "0X000002B6")
        self.assertEqual(artifact.registers["USART1_CR1"].upper(), "0X0000000D")
        self.assertTrue(artifact.sources.gdb.embedded)
        self.assertTrue(artifact.sources.rtt.embedded)
        self.assertTrue(artifact.sources.registers.embedded)
        self.assertEqual(artifact.sources.gdb.event_count, 3)
        self.assertEqual(artifact.sources.registers.register_count, 5)
        self.assertEqual(
            [item.name for item in artifact.sources.registers.peripherals],
            ["RCC", "USART1"],
        )
        self.assertIn("serial_path=fault code=-2", artifact.sources.rtt.raw_text)
        self.assertTrue(data["_fabricated"])
        self.assertIn("project-authored", data["provenance"]["note"])

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

    def test_peripheral_demo_includes_project_owned_reference_pdf(self):
        source_path = (
            PERIPHERAL_DEMO_ROOT / "doc" / "debugoracle_demo_stm32l4_reference.md"
        )
        pdf_path = source_path.with_suffix(".pdf")

        self.assertTrue(source_path.is_file())
        self.assertTrue(pdf_path.is_file())
        self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))

        source = source_path.read_text(encoding="utf-8")
        for required_text in (
            "Project-owned demo reference",
            "RCC_CCIPR",
            "USART1SEL",
            "USART_BRR",
            "not a replacement for RM0394",
            "https://www.st.com/en/microcontrollers-microprocessors/stm32l4-series/documentation.html",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, source)

    def test_peripheral_demo_reference_is_ingestible_and_searchable(self):
        source_pdf = (
            PERIPHERAL_DEMO_ROOT / "doc" / "debugoracle_demo_stm32l4_reference.pdf"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            docs_dir = workspace / "docs" / "vendor"
            docs_dir.mkdir(parents=True)
            shutil.copy2(source_pdf, docs_dir / source_pdf.name)

            ingest_stdout = StringIO()
            with redirect_stdout(ingest_stdout), redirect_stderr(StringIO()):
                ingest_code = cli_main(
                    [
                        "docs",
                        "ingest",
                        "--workspace-root",
                        str(workspace),
                        "--yes",
                        "--no-interactive",
                        "--format",
                        "json",
                    ]
                )
            ingest_payload = json.loads(ingest_stdout.getvalue())

            search_stdout = StringIO()
            with redirect_stdout(search_stdout), redirect_stderr(StringIO()):
                search_code = cli_main(
                    [
                        "docs",
                        "search",
                        "USART1SEL USART_BRR baud",
                        "--workspace-root",
                        str(workspace),
                        "--format",
                        "json",
                    ]
                )
            search_payload = json.loads(search_stdout.getvalue())

        self.assertEqual(ingest_code, 0)
        self.assertEqual(ingest_payload["results"][0]["ingest_state"], "clean")
        self.assertEqual(ingest_payload["results"][0]["page_count"], 2)
        self.assertEqual(search_code, 0)
        self.assertGreater(len(search_payload["results"]), 0)
        self.assertIn("USART_BRR", search_payload["results"][0]["text"])

    def test_peripheral_demo_committed_report_matches_snapshot(self):
        snapshot_path = self._snapshot_path("peripheral-miscfg")
        report_path = snapshot_path.with_name("report.txt")

        code, stdout, stderr = self._run_report(snapshot_path)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, report_path.read_text(encoding="utf-8"))
        self.assertIn("Trust: SAFE", stdout)
        self.assertIn("RCC_CCIPR: 0x00000002", stdout)
        self.assertIn("USART1_BRR: 0x000002B6", stdout)

    def test_peripheral_demo_explains_automatic_docs_and_svd_setup(self):
        readme = (PERIPHERAL_DEMO_ROOT / "README.md").read_text(encoding="utf-8")
        agent_guide = (PERIPHERAL_DEMO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        vendor_guide = (STM32_WORKSPACES_ROOT / "vendor-downloads.md").read_text(
            encoding="utf-8"
        )

        for document in (readme, agent_guide, vendor_guide):
            self.assertIn("docs/vendor/", document)
            self.assertIn(".dbgoracle/", document)

        self.assertIn("dbgoracle docs ingest --workspace-root . --yes", agent_guide)
        self.assertIn("dbgoracle init-workspace", agent_guide)
        self.assertIn("initialise this workspace", readme.lower())
        self.assertIn("RM0394", vendor_guide)
