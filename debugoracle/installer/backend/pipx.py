from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path

from ..outcomes import InstallState
from ..versioning import VersioningError, compare_versions


class PipxError(RuntimeError):
    pass


@dataclass(slots=True)
class InstallationStatus:
    state: InstallState
    installed_version: str | None = None
    binary_path: str | None = None


class PipxBackend:
    def __init__(self, *, env: dict[str, str] | None = None) -> None:
        self._env = dict(os.environ if env is None else env)

    def is_available(self) -> bool:
        return shutil.which("pipx", path=self._env.get("PATH")) is not None

    def bin_dir(self) -> Path:
        configured = self._env.get("PIPX_BIN_DIR")
        if configured:
            return Path(configured).expanduser()
        completed = self._run(["pipx", "environment", "--value", "PIPX_BIN_DIR"])
        resolved = completed.stdout.strip()
        if not resolved:
            raise PipxError("pipx did not report its application binary directory")
        return Path(resolved).expanduser()

    def inspect_installation(
        self, package_name: str, target_version: str
    ) -> InstallationStatus:
        payload = self._run_json(["pipx", "list", "--json"])
        venvs = payload.get("venvs") if isinstance(payload, dict) else None
        if not isinstance(venvs, dict) or package_name not in venvs:
            return InstallationStatus(state=InstallState.NOT_INSTALLED)
        metadata = venvs[package_name].get("metadata", {})
        main_package = (
            metadata.get("main_package", {}) if isinstance(metadata, dict) else {}
        )
        installed_version = None
        if isinstance(main_package, dict):
            candidate = main_package.get("package_version")
            if isinstance(candidate, str) and candidate.strip():
                installed_version = candidate
        binary_path = str(self.bin_dir() / "dbgoracle")
        try:
            if installed_version is None:
                state = InstallState.INSTALL_IN_PROGRESS
            else:
                comparison = compare_versions(installed_version, target_version)
                if comparison == 0:
                    state = InstallState.INSTALLED_SAME_VERSION
                elif comparison < 0:
                    state = InstallState.INSTALLED_OLDER_VERSION
                else:
                    state = InstallState.INSTALLED_NEWER_VERSION
        except VersioningError as error:
            raise PipxError(
                f"pipx reported invalid version metadata: {error}"
            ) from error
        return InstallationStatus(
            state=state, installed_version=installed_version, binary_path=binary_path
        )

    def install(self, source_spec: str, *, force: bool = False) -> None:
        command = ["pipx", "install"]
        if force:
            command.append("--force")
        command.append(source_spec)
        self._run(command)

    def upgrade(self, package_name: str, source_spec: str | None = None) -> None:
        if source_spec:
            self.install(source_spec, force=True)
            return
        self._run(["pipx", "upgrade", package_name])

    def uninstall(self, package_name: str) -> None:
        self._run(["pipx", "uninstall", package_name])

    def verify_cli(
        self,
        binary_name: str,
        *,
        binary_path: str | None = None,
        expected_version: str | None = None,
    ) -> tuple[bool, str]:
        binary = binary_path
        if binary is None:
            binary = shutil.which(binary_name, path=self._env.get("PATH"))
            if binary is None:
                candidate = self.bin_dir() / binary_name
                if candidate.is_file():
                    binary = str(candidate)
        if binary is None:
            return False, "Installed binary is not discoverable"
        try:
            completed = subprocess.run(  # nosec B603
                [binary, "--version"],
                check=False,
                capture_output=True,
                text=True,
                env=self._env,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return False, f"Unable to run installed CLI: {error}"
        if completed.returncode != 0:
            return False, (
                completed.stderr or completed.stdout or "version check failed"
            ).strip()
        output = (completed.stdout or completed.stderr).strip()
        if expected_version is not None and output != expected_version:
            return False, f"Installed binary reports unexpected version: {output}"
        return True, output

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(  # nosec B603
                command, check=False, capture_output=True, text=True, env=self._env
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PipxError(f"Unable to run pipx: {error}") from error
        if completed.returncode != 0:
            raise PipxError(
                (completed.stderr or completed.stdout or "pipx command failed").strip()
            )
        return completed

    def _run_json(self, command: list[str]) -> dict[str, object]:
        completed = self._run(command)
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as error:
            raise PipxError(f"Unable to parse pipx JSON output: {error}") from error
        if not isinstance(payload, dict):
            raise PipxError("Unexpected pipx JSON payload")
        return payload
