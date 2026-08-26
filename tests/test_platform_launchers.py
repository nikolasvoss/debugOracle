from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "macOS launcher execution is verified on macOS")
class MacosLauncherTests(unittest.TestCase):
    def test_checkout_launcher_forwards_arguments_to_shared_bootstrap(self) -> None:
        launcher = REPOSITORY_ROOT / "scripts" / "install" / "macos.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            capture_path = Path(tmpdir) / "arguments.json"
            python_shim = Path(tmpdir) / "python-shim"
            python_shim.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "import os\n"
                "import sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['ARGUMENT_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            python_shim.chmod(python_shim.stat().st_mode | stat.S_IXUSR)
            environment = dict(os.environ)
            environment["PYTHON_BIN"] = str(python_shim)
            environment["ARGUMENT_CAPTURE"] = str(capture_path)

            completed = subprocess.run(
                ["bash", str(launcher), "--docs-tools", "none"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            forwarded = json.loads(capture_path.read_text(encoding="utf-8"))
            self.assertEqual(
                forwarded[0],
                str(REPOSITORY_ROOT / "scripts" / "install" / "bootstrap.py"),
            )
            self.assertEqual(forwarded[1:], ["--docs-tools", "none"])

    def test_checkout_uninstaller_forwards_arguments_to_shared_uninstaller(
        self,
    ) -> None:
        launcher = REPOSITORY_ROOT / "scripts" / "install" / "uninstall-macos.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            capture_path = Path(tmpdir) / "arguments.json"
            python_shim = _write_python_shim(Path(tmpdir), capture_path)
            environment = dict(os.environ)
            environment["PYTHON_BIN"] = str(python_shim)
            environment["ARGUMENT_CAPTURE"] = str(capture_path)

            completed = subprocess.run(
                ["bash", str(launcher), "--keep-path"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            forwarded = json.loads(capture_path.read_text(encoding="utf-8"))
            self.assertEqual(
                forwarded[0],
                str(REPOSITORY_ROOT / "scripts" / "install" / "uninstall.py"),
            )
            self.assertEqual(forwarded[1:], ["--keep-path"])


class WindowsLauncherContractTests(unittest.TestCase):
    def test_installer_uses_direct_argument_forwarding_without_policy_bypass(
        self,
    ) -> None:
        launcher = REPOSITORY_ROOT / "scripts" / "install" / "windows.ps1"

        content = launcher.read_text(encoding="utf-8")

        self.assertIn("bootstrap.py", content)
        self.assertIn("@RemainingArgs", content)
        self.assertNotIn("Invoke-Expression", content)
        self.assertNotIn("ExecutionPolicy", content)

    def test_uninstaller_uses_direct_argument_forwarding_without_policy_bypass(
        self,
    ) -> None:
        launcher = REPOSITORY_ROOT / "scripts" / "install" / "uninstall-windows.ps1"

        content = launcher.read_text(encoding="utf-8")

        self.assertIn("uninstall.py", content)
        self.assertIn("@RemainingArgs", content)
        self.assertNotIn("Invoke-Expression", content)
        self.assertNotIn("ExecutionPolicy", content)


def _write_python_shim(directory: Path, capture_path: Path) -> Path:
    python_shim = directory / "python-shim"
    python_shim.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['ARGUMENT_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    python_shim.chmod(python_shim.stat().st_mode | stat.S_IXUSR)
    return python_shim


if __name__ == "__main__":
    unittest.main()
