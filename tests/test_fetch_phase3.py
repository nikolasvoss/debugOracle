from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path

from debugoracle.builder import build_bundle_from_text
from debugoracle.cli import main
from debugoracle.cli.main import build_parser


FIXTURES = Path(__file__).parent / "fixtures"


class FetchPhase3Tests(unittest.TestCase):
    def test_fetch_command_replaces_observe_and_snapshot(self) -> None:
        parser = build_parser()

        fetch_args = parser.parse_args(["fetch", "--gdb-mi", "sample.mi"])
        self.assertEqual(fetch_args.command, "fetch")

        with self.assertRaises(SystemExit):
            parser.parse_args(["observe"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["snapshot"])

    def test_fetch_writes_latest_snapshot_and_prints_operational_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "cortex-debug-shared-mi.log").write_text(
                (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (workspace / "session.rtt").write_text(
                (FIXTURES / "sample.rtt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            previous = os.getcwd()
            try:
                os.chdir(workspace)
                stdout, stderr = self._run_cli(["fetch"], capture_stderr=True)
            finally:
                os.chdir(previous)

            snapshot_path = workspace / "latest_snapshot.json"
            self.assertTrue(snapshot_path.exists())
            self.assertIn("Snapshot ID:", stdout)
            self.assertIn("Output Path:", stdout)
            self.assertIn(str(snapshot_path), stdout)
            self.assertIn("Embedded Sources: gdb, rtt", stdout)
            self.assertIn("Source Sizes/Counts:", stdout)
            self.assertIn("- gdb:", stdout)
            self.assertIn("- rtt:", stdout)
            self.assertIn("Auto-discovered input paths for fetch:", stderr)

    def test_fetch_discovery_failure_lists_checked_raw_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                code, stdout, stderr = self._run_cli_expect_system_exit(["fetch"])
            finally:
                os.chdir(previous)

        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("could not auto-resolve an input source", message)
        self.assertIn("cortex-debug-shared-mi.log", message)
        self.assertIn("session.rtt", message)
        self.assertNotIn("--snapshot-file", message)
        self.assertNotIn("latest_snapshot.json", message)

    def test_snapshot_keeps_full_embedded_rtt_when_recent_window_is_trimmed(self) -> None:
        bundle = build_bundle_from_text("^done\n", "line one\nline two\nline three\n", rtt_window=2)

        self.assertEqual(bundle.recent_rtt, ["line two", "line three"])
        self.assertEqual(bundle.sources.rtt.lines, ["line one", "line two", "line three"])
        self.assertEqual(bundle.sources.rtt.raw_text, "line one\nline two\nline three\n")

    def _run_cli(
        self,
        argv: list[str],
        *,
        capture_stderr: bool = False,
    ) -> str | tuple[str, str]:
        buffer = io.StringIO()
        if capture_stderr:
            stderr = io.StringIO()
            with redirect_stdout(buffer), redirect_stderr(stderr):
                exit_code = main(argv)
            self.assertEqual(exit_code, 0)
            return buffer.getvalue(), stderr.getvalue()
        with redirect_stdout(buffer):
            exit_code = main(argv)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def _run_cli_expect_system_exit(
        self,
        argv: list[str],
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as error:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main(argv)
        exit_payload = error.exception.code
        stderr_text = stderr.getvalue()
        if not isinstance(exit_payload, int) and exit_payload is not None:
            exit_text = str(exit_payload)
            if exit_text:
                stderr_text = (
                    f"{stderr_text.rstrip()}\n{exit_text}\n"
                    if stderr_text
                    else f"{exit_text}\n"
                )
        return (
            exit_payload if isinstance(exit_payload, int) else 1,
            stdout.getvalue(),
            stderr_text,
        )


if __name__ == "__main__":
    unittest.main()
