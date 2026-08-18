from __future__ import annotations

import unittest
from unittest.mock import patch

from debugoracle.diagnostics import collect_docs_doctor_checks


class DocsDiagnosticsTests(unittest.TestCase):
    def test_docs_doctor_requires_pypdf_as_the_only_base_pdf_dependency(self) -> None:
        with patch(
            "debugoracle.diagnostics.importlib.util.find_spec", return_value=None
        ):
            checks = collect_docs_doctor_checks(
                python_executable="/opt/debug oracle/bin/python"
            )

        required = [check for check in checks if check.required]
        self.assertEqual([check.key for check in required], ["pypdf"])
        self.assertEqual(
            required[0].remedy,
            "'/opt/debug oracle/bin/python' -m pip install pypdf",
        )
        rendered = "\n".join(
            f"{check.key} {check.detail} {check.remedy}" for check in checks
        ).lower()
        self.assertNotIn("pymupdf", rendered)


if __name__ == "__main__":
    unittest.main()
