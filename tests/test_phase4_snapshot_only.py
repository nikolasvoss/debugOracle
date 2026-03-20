from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout

from debugoracle.cli import main
from debugoracle.cli.main import build_parser


class Phase4SnapshotOnlyTests(unittest.TestCase):
    def test_report_requires_snapshot_and_rejects_raw_inputs(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["report", "--gdb-mi", "sample.mi"])

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                code, stdout, stderr = self._run_cli_expect_system_exit(["report"])
            finally:
                os.chdir(previous)

        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("report requires a snapshot", message)
        self.assertIn("run `fetch`", message)


    def test_prompt_requires_snapshot_and_rejects_raw_inputs(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["prompt", "--goal", "Explain stop", "--gdb-mi", "sample.mi"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["prompt", "--goal", "Explain stop", "--rtt-window", "5"])

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            try:
                os.chdir(tmpdir)
                code, stdout, stderr = self._run_cli_expect_system_exit(["prompt", "--goal", "Explain stop"])
            finally:
                os.chdir(previous)

        self.assertNotEqual(code, 0)
        message = (stdout + stderr).strip()
        self.assertIn("prompt requires a snapshot", message)
        self.assertIn("run `fetch`", message)

    def _run_cli_expect_system_exit(self, argv: list[str]) -> tuple[int, str, str]:
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
                    f"{stderr_text.rstrip()}\n{exit_text}\n" if stderr_text else f"{exit_text}\n"
                )
        return (exit_payload if isinstance(exit_payload, int) else 1, stdout.getvalue(), stderr_text)


if __name__ == "__main__":
    unittest.main()
