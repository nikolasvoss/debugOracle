from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "verify-release.sh"


class ReleaseVerificationScriptTests(unittest.TestCase):
    def test_release_check_rejects_path_arguments_before_any_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkout = Path(tmpdir) / "checkout"
            scripts = checkout / "scripts"
            fake_bin = Path(tmpdir) / "bin"
            scripts.mkdir(parents=True)
            fake_bin.mkdir()
            shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)

            verification_marker = Path(tmpdir) / "verification-started"
            verify_script = scripts / "verify.sh"
            verify_script.write_text(
                f"#!/usr/bin/env bash\ntouch '{verification_marker}'\n",
                encoding="utf-8",
            )
            verify_script.chmod(0o755)
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            environment.pop("DEBUGORACLE_SKIP_PRIVATE_REFERENCE", None)
            environment.pop("DEBUGORACLE_RELEASE_TAG", None)
            completed = subprocess.run(
                ["bash", str(scripts / SCRIPT_PATH.name), "/"],
                cwd=checkout,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Usage: ./scripts/verify-release.sh", completed.stderr)
        self.assertFalse(verification_marker.exists())

    def test_missing_recursive_submodule_fails_before_release_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkout = Path(tmpdir) / "checkout"
            scripts = checkout / "scripts"
            fake_bin = Path(tmpdir) / "bin"
            scripts.mkdir(parents=True)
            fake_bin.mkdir()
            shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)

            verification_marker = Path(tmpdir) / "verification-started"
            verify_script = scripts / "verify.sh"
            verify_script.write_text(
                f"#!/usr/bin/env bash\ntouch '{verification_marker}'\n",
                encoding="utf-8",
            )
            verify_script.chmod(0o755)

            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' "
                "'-0000000000000000000000000000000000000000 examples/missing'\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            environment.pop("DEBUGORACLE_SKIP_PRIVATE_REFERENCE", None)
            environment.pop("DEBUGORACLE_RELEASE_TAG", None)
            completed = subprocess.run(
                ["bash", str(scripts / SCRIPT_PATH.name)],
                cwd=checkout,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("git submodule update --init --recursive", completed.stderr)
        self.assertFalse(verification_marker.exists())

    def test_explicit_non_tag_ci_exception_skips_private_reference_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkout = Path(tmpdir) / "checkout"
            scripts = checkout / "scripts"
            fake_bin = Path(tmpdir) / "bin"
            scripts.mkdir(parents=True)
            fake_bin.mkdir()
            shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)

            verification_marker = Path(tmpdir) / "verification-started"
            verify_script = scripts / "verify.sh"
            verify_script.write_text(
                f"#!/usr/bin/env bash\ntouch '{verification_marker}'\nexit 7\n",
                encoding="utf-8",
            )
            verify_script.chmod(0o755)

            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' "
                "'-0000000000000000000000000000000000000000 examples/missing'\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            environment["DEBUGORACLE_SKIP_PRIVATE_REFERENCE"] = "1"
            environment.pop("DEBUGORACLE_RELEASE_TAG", None)
            completed = subprocess.run(
                ["bash", str(scripts / SCRIPT_PATH.name)],
                cwd=checkout,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            verification_started = verification_marker.exists()

        self.assertEqual(completed.returncode, 7)
        self.assertIn("private reference-workspace gate is deferred", completed.stderr)
        self.assertTrue(verification_started)

    def test_tagged_release_rejects_private_reference_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkout = Path(tmpdir) / "checkout"
            scripts = checkout / "scripts"
            fake_bin = Path(tmpdir) / "bin"
            scripts.mkdir(parents=True)
            fake_bin.mkdir()
            shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)

            verification_marker = Path(tmpdir) / "verification-started"
            verify_script = scripts / "verify.sh"
            verify_script.write_text(
                f"#!/usr/bin/env bash\ntouch '{verification_marker}'\n",
                encoding="utf-8",
            )
            verify_script.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            environment["DEBUGORACLE_SKIP_PRIVATE_REFERENCE"] = "1"
            environment["DEBUGORACLE_RELEASE_TAG"] = "v0.3.1"
            completed = subprocess.run(
                ["bash", str(scripts / SCRIPT_PATH.name)],
                cwd=checkout,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            verification_started = verification_marker.exists()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("tagged release cannot skip", completed.stderr)
        self.assertFalse(verification_started)

    def test_complete_release_check_builds_validates_installs_and_smokes_wheel(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkout = Path(tmpdir) / "checkout"
            scripts = checkout / "scripts"
            fake_bin = Path(tmpdir) / "bin"
            release_tmp = Path(tmpdir) / "release-tmp"
            command_log = Path(tmpdir) / "commands.log"
            scripts.mkdir(parents=True)
            fake_bin.mkdir()
            release_tmp.mkdir()
            shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)

            verify_script = scripts / "verify.sh"
            verify_script.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'verify %s\\n' \"$*\" >> '{command_log}'\n",
                encoding="utf-8",
            )
            verify_script.chmod(0o755)

            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/usr/bin/env bash\n"
                "printf ' 0123456789012345678901234567890123456789 examples/pinned\\n'\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)

            fake_python = fake_bin / "release-python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"printf 'python %s\\n' \"$*\" >> '{command_log}'\n"
                f"printf 'umask %s\\n' \"$(umask)\" >> '{command_log}'\n"
                "if [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'build' ]; then\n"
                "  while [ \"${1:-}\" != '--outdir' ]; do shift; done\n"
                '  mkdir -p "$2"\n'
                '  touch "$2/debugoracle-0.3.1-py3-none-any.whl"\n'
                '  touch "$2/debugoracle-0.3.1.tar.gz"\n'
                "elif [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'zipfile' ]; then\n"
                "  printf '%s\\n' 'debugoracle/__init__.py'\n"
                "  printf '%s\\n' 'debugoracle-0.3.1.dist-info/licenses/LICENSE'\n"
                "  printf '%s\\n' 'debugoracle-0.3.1.dist-info/entry_points.txt'\n"
                "elif [ \"${1:-}\" = '-m' ] && [ \"${2:-}\" = 'venv' ]; then\n"
                '  venv_dir="$3"\n'
                '  mkdir -p "$venv_dir/bin"\n'
                f"  printf '%s\\n' '#!/usr/bin/env bash' \"printf 'venv-python %s\\\\n' \\\"\\$*\\\" >> '{command_log}'\" > \"$venv_dir/bin/python\"\n"
                "  printf '%s\\n' '#!/usr/bin/env bash' 'case \"$1\" in --version) echo 0.3.1 ;; --help) echo usage: dbgoracle ;; *) exit 2 ;; esac' > \"$venv_dir/bin/dbgoracle\"\n"
                '  chmod 755 "$venv_dir/bin/python" "$venv_dir/bin/dbgoracle"\n'
                "fi\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            environment["PYTHON"] = str(fake_python)
            environment["TMPDIR"] = str(release_tmp)
            environment.pop("DEBUGORACLE_SKIP_PRIVATE_REFERENCE", None)
            environment.pop("DEBUGORACLE_RELEASE_TAG", None)
            completed = subprocess.run(
                ["bash", str(scripts / SCRIPT_PATH.name)],
                cwd=checkout,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                preexec_fn=lambda: os.umask(0o077),
            )
            logged_commands = command_log.read_text(encoding="utf-8")
            retained_release_directories = list(
                release_tmp.glob("debugoracle-release.*")
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("verify full", logged_commands)
        self.assertIn("umask 0022", logged_commands)
        self.assertEqual(logged_commands.count("python -m build"), 2)
        self.assertIn("python -m twine check", logged_commands)
        self.assertIn("venv-python -m pip install", logged_commands)
        self.assertIn("Release verification complete", completed.stdout)
        self.assertEqual(retained_release_directories, [])

        script_text = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("SOURCE_DATE_EPOCH", script_text)
        self.assertIn("1787529600", script_text)
        self.assertIn('"${DEBUGORACLE_RELEASE_TAG:-}"', script_text)
        self.assertIn("if release_tag:", script_text)
        self.assertIn('manifest["artifact_sha256"]', script_text)
        self.assertIn('manifest["artifact_size"]', script_text)


if __name__ == "__main__":
    unittest.main()
