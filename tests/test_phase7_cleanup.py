from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from debugoracle.cli.main import build_parser


class Phase7CleanupTests(unittest.TestCase):
    def test_report_rejects_removed_legacy_flags_but_prompt_keeps_prompt_variable_controls(self) -> None:
        parser = build_parser()

        for argv in (
            ["report", "--var-scope", "all"],
            ["report", "--var-name", "system_state"],
            ["report", "--var-detail", "full"],
            ["report", "--format", "text"],
        ):
            with self.assertRaises(SystemExit):
                parser.parse_args(argv)

        prompt_args = parser.parse_args(["prompt", "--goal", "Explain stop", "--var-scope", "all"])
        self.assertEqual(prompt_args.var_scope, "all")

    def test_fetch_and_report_help_no_longer_advertise_raw_export_sidecars(self) -> None:
        parser = build_parser()

        fetch_help = self._format_help(parser, ["fetch", "--help"])
        report_help = self._format_help(parser, ["report", "--help"])

        self.assertNotIn("--export-raw", fetch_help)
        self.assertNotIn("sidecar", fetch_help.lower())
        self.assertNotIn("--export-raw", report_help)
        self.assertNotIn("sidecar", report_help.lower())

    def _format_help(self, parser, argv: list[str]) -> str:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                parser.parse_args(argv)
        return stdout.getvalue() + stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
