from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "render-runtime-requirements.py"


class RuntimeRequirementsTests(unittest.TestCase):
    def test_renderer_emits_one_declared_runtime_requirement_per_line(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.splitlines(), ["packaging==26.0", "pypdf==6.16.1"]
        )
