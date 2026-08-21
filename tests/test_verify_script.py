from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


class VerifyScriptTests(unittest.TestCase):
    def test_default_mode_runs_fast_pass_with_tests_and_without_coverage(
        self,
    ) -> None:
        script_path = Path("scripts/verify.sh")
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            log_path = Path(tmp) / "pre_commit.log"
            bin_dir.mkdir(parents=True, exist_ok=True)

            pre_commit = bin_dir / "pre-commit"
            pre_commit.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f'echo "SKIP=${{SKIP-}} PYTEST_ADDOPTS=${{PYTEST_ADDOPTS-}} ARGS:$*" > {log_path}\n',
                encoding="utf-8",
            )
            pre_commit.chmod(pre_commit.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

            completed = subprocess.run(
                ["/bin/bash", str(script_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(log_path.exists(), "expected fake pre-commit to run")
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("SKIP=coverage", log_text)
            self.assertNotIn("SKIP=coverage,pytest-fast", log_text)
            self.assertIn(
                "PYTEST_ADDOPTS=--ignore=tests/debugoracle-hil-tests", log_text
            )
            self.assertIn("ARGS:run --all-files", log_text)
            self.assertIn(
                "Fast preflight complete. Run ./scripts/verify.sh full before completion.",
                completed.stdout,
            )

    def test_full_mode_skips_fast_test_hook(self) -> None:
        script_path = Path("scripts/verify.sh")
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            log_path = Path(tmp) / "pre_commit.log"
            bin_dir.mkdir(parents=True, exist_ok=True)

            pre_commit = bin_dir / "pre-commit"
            pre_commit.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f'echo "SKIP=${{SKIP-}} PYTEST_ADDOPTS=${{PYTEST_ADDOPTS-}} ARGS:$*" > {log_path}\n',
                encoding="utf-8",
            )
            pre_commit.chmod(pre_commit.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

            completed = subprocess.run(
                ["/bin/bash", str(script_path), "full"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(log_path.exists(), "expected fake pre-commit to run")
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("SKIP=", log_text)
            self.assertIn("SKIP=pytest-fast", log_text)
            self.assertNotIn("SKIP=coverage", log_text)
            self.assertIn(
                "PYTEST_ADDOPTS=--ignore=tests/debugoracle-hil-tests", log_text
            )
            self.assertIn("ARGS:run --all-files", log_text)

    def test_quality_configuration_has_fast_and_coverage_test_hooks(self) -> None:
        config = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")

        self.assertIn("- id: coverage", config)
        self.assertIn("- id: pytest-fast", config)

    def test_invalid_mode_returns_usage_error(self) -> None:
        script_path = Path("scripts/verify.sh")
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)

            pre_commit = bin_dir / "pre-commit"
            pre_commit.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
                encoding="utf-8",
            )
            pre_commit.chmod(pre_commit.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

            completed = subprocess.run(
                ["/bin/bash", str(script_path), "nope"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("Usage: ./scripts/verify.sh [fast|full]", completed.stderr)

    def test_invalid_mode_returns_usage_even_without_pre_commit(self) -> None:
        script_path = Path("scripts/verify.sh")
        env = os.environ.copy()
        env["PATH"] = "/nonexistent"

        completed = subprocess.run(
            ["/bin/bash", str(script_path), "nope"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Usage: ./scripts/verify.sh [fast|full]", completed.stderr)

    def test_missing_pre_commit_returns_actionable_error(self) -> None:
        script_path = Path("scripts/verify.sh")
        env = os.environ.copy()
        env["PATH"] = "/nonexistent"

        completed = subprocess.run(
            ["/bin/bash", str(script_path)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("pre-commit is required.", completed.stderr)
        self.assertIn("python -m pip install pre-commit", completed.stderr)


if __name__ == "__main__":
    unittest.main()
