from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .backend.pipx import InstallationStatus, PipxBackend, PipxError
from .manifest import ManifestError, ManifestFetcher, ManifestNetworkError, ReleaseManifest
from .outcomes import InstallState, InstallerOutcome, InstallerOutcomeCode, PathAction
from .platform import linux as linux_platform

INSTALLER_VERSION = "0.1.0"
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/nikolasvoss/ai-debugger-v2/main/release/install-manifest.json"
DEFAULT_BINARY_NAME = "dbgoracle"


@dataclass(slots=True)
class InstallerOptions:
    manifest_url: str | None = DEFAULT_MANIFEST_URL
    channel: str = "stable"
    package_source_override: str | None = None
    assume_yes: bool = False
    doctor: bool = True


class InstallerCore:
    def __init__(
        self,
        *,
        backend: PipxBackend,
        fetcher: ManifestFetcher,
        env: dict[str, str] | None = None,
        python_version: tuple[int, int, int] | None = None,
        sleep: Callable[[float], None] | None = None,
        input_func: Callable[[str], str] | None = None,
    ) -> None:
        self.backend = backend
        self.fetcher = fetcher
        self.env = dict(os.environ if env is None else env)
        self.python_version = python_version or sys.version_info[:3]
        self.sleep = sleep or time.sleep
        self.input_func = input_func or input

    def run(self, options: InstallerOptions) -> InstallerOutcome:
        if not sys.platform.startswith("linux"):
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_PLATFORM,
                message="Linux v1 installer support is the only supported platform right now.",
                details=[f"Detected platform: {sys.platform}"],
            )
        if self.python_version < (3, 10, 0):
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MISSING_PYTHON,
                message="DebugOracle requires Python 3.10 or newer.",
                details=[f"Detected Python: {'.'.join(str(part) for part in self.python_version)}"],
            )
        if not self.backend.is_available():
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MISSING_PIPX,
                message="pipx is required for the Linux v1 installer.",
                details=["Install pipx first, then rerun the installer."],
            )

        manifest_url = options.manifest_url or DEFAULT_MANIFEST_URL
        try:
            manifest = self._fetch_manifest_with_retry(manifest_url)
        except ManifestError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MANIFEST,
                message="The installer manifest is invalid.",
                details=[str(error)],
            )
        except ManifestNetworkError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.FAILED_NETWORK_TRANSIENT,
                message="Unable to fetch the installer manifest after retrying once.",
                details=[str(error)],
            )

        if manifest.channel != options.channel:
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MANIFEST,
                message="The installer manifest channel did not match the requested channel.",
                details=[f"Expected {options.channel}, got {manifest.channel}"],
            )
        if not _python_satisfies(self.python_version, manifest.python_requires):
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MISSING_PYTHON,
                message="Your Python version does not satisfy the release requirements.",
                details=[
                    f"Detected Python: {'.'.join(str(part) for part in self.python_version)}",
                    f"Required: {manifest.python_requires}",
                ],
            )
        if _compare_versions(INSTALLER_VERSION, manifest.installer_min_version) < 0:
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MANIFEST,
                message="This installer is older than the minimum supported installer version.",
                details=[
                    f"Installer version: {INSTALLER_VERSION}",
                    f"Required installer version: {manifest.installer_min_version}",
                ],
            )

        try:
            current = self.backend.inspect_installation(manifest.package_name, manifest.version)
        except PipxError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.FAILED_INSTALL,
                message="Unable to inspect the current pipx installation state.",
                details=[str(error)],
            )

        if current.state in {InstallState.INSTALLED_SAME_VERSION, InstallState.INSTALLED_NEWER_VERSION}:
            verified, verify_message = self._verify_status_binary(current, current.installed_version or manifest.version)
            if not verified:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_VERIFY,
                    message="The existing dbgoracle installation could not be verified.",
                    version=manifest.version,
                    installed_version=current.installed_version,
                    details=[verify_message],
                )
            outcome = InstallerOutcome(
                code=InstallerOutcomeCode.SUCCESS_ALREADY_INSTALLED,
                message=f"dbgoracle already installed at {current.installed_version or manifest.version}.",
                version=manifest.version,
                installed_version=current.installed_version,
                details=[verify_message] if verify_message else [],
            )
            self._finalize_success(outcome, current, options)
            return outcome

        source_spec = options.package_source_override or manifest.source_url or f"{manifest.package_name}=={manifest.version}"
        try:
            if current.state == InstallState.INSTALLED_OLDER_VERSION:
                self.backend.upgrade(manifest.package_name, source_spec)
                action = InstallerOutcomeCode.SUCCESS_UPGRADED
                success_message = f"dbgoracle upgraded to {manifest.version}."
            else:
                self.backend.install(source_spec)
                action = InstallerOutcomeCode.SUCCESS_INSTALLED
                success_message = f"dbgoracle {manifest.version} installed successfully."
        except PipxError as error:
            return self._handle_install_failure(error, manifest, current)

        post_install = self.backend.inspect_installation(manifest.package_name, manifest.version)
        verified, verify_message = self._verify_status_binary(post_install, manifest.version)
        if not verified:
            return self._handle_verify_failure(manifest, current, verify_message)
        outcome = InstallerOutcome(
            code=action,
            message=success_message,
            version=manifest.version,
            installed_version=post_install.installed_version,
            details=[verify_message] if verify_message else [],
        )
        self._finalize_success(outcome, post_install, options)
        return outcome

    def _fetch_manifest_with_retry(self, manifest_url: str) -> ReleaseManifest:
        try:
            return self.fetcher.fetch(manifest_url)
        except ManifestNetworkError:
            self.sleep(0.1)
            return self.fetcher.fetch(manifest_url)

    def _handle_install_failure(
        self,
        error: PipxError,
        manifest: ReleaseManifest,
        current: InstallationStatus,
    ) -> InstallerOutcome:
        if current.state == InstallState.NOT_INSTALLED:
            try:
                self.backend.uninstall(manifest.package_name)
            except PipxError as cleanup_error:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="Install failed and cleanup could not confirm a clean state.",
                    version=manifest.version,
                    details=[str(error), str(cleanup_error)],
                )
        else:
            try:
                restored = self.backend.inspect_installation(manifest.package_name, current.installed_version or "0")
            except PipxError as inspect_error:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="Upgrade failed and the previous installation could not be verified.",
                    version=manifest.version,
                    details=[str(error), str(inspect_error)],
                )
            if restored.installed_version != current.installed_version:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="Upgrade failed and the previous working version was not preserved.",
                    version=manifest.version,
                    details=[str(error)],
                )
        return InstallerOutcome(
            code=InstallerOutcomeCode.FAILED_INSTALL,
            message="pipx could not complete the install step.",
            version=manifest.version,
            details=[str(error)],
        )

    def _handle_verify_failure(
        self,
        manifest: ReleaseManifest,
        current: InstallationStatus,
        verify_message: str,
    ) -> InstallerOutcome:
        if current.state == InstallState.NOT_INSTALLED:
            try:
                self.backend.uninstall(manifest.package_name)
            except PipxError as cleanup_error:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="CLI verification failed and cleanup also failed.",
                    version=manifest.version,
                    details=[verify_message, str(cleanup_error)],
                )
        else:
            restored = self.backend.inspect_installation(manifest.package_name, current.installed_version or "0")
            if restored.installed_version != current.installed_version:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="CLI verification failed and the previous installation was not preserved.",
                    version=manifest.version,
                    details=[verify_message],
                )
        return InstallerOutcome(
            code=InstallerOutcomeCode.FAILED_VERIFY,
            message="The CLI installed, but the post-install verification step failed.",
            version=manifest.version,
            details=[verify_message],
        )

    def _finalize_success(
        self,
        outcome: InstallerOutcome,
        status: InstallationStatus,
        options: InstallerOptions,
    ) -> None:
        if options.doctor:
            outcome.doctor_notes.extend(_doctor_notes(self.env))
        binary_path = status.binary_path or str(self.backend.bin_dir() / DEFAULT_BINARY_NAME)
        binary_dir = Path(binary_path).parent
        if self._is_binary_discoverable(binary_path):
            return
        home = Path(self.env.get("HOME", str(Path.home()))).expanduser()
        plan = linux_platform.build_path_plan(binary_dir, self.env.get("SHELL"), home, self.env)
        path_action = PathAction(
            bin_dir=str(plan.bin_dir),
            profile_path=str(plan.profile_path) if plan.profile_path else None,
            export_line=plan.export_line,
        )
        accepted = False
        if options.assume_yes and plan.profile_path and plan.export_line:
            accepted = True
        elif sys.stdin.isatty() and plan.profile_path and plan.export_line:
            prompt = f"dbgoracle is installed, but {plan.bin_dir} is not on PATH. Add it to {plan.profile_path}? [y/N] "
            accepted = self.input_func(prompt).strip().lower() in {"y", "yes"}
        else:
            path_action.declined = True
        if accepted and plan.profile_path and plan.export_line:
            applied, error = linux_platform.append_path_line(plan.profile_path, plan.export_line)
            path_action.applied = applied
            path_action.error = error
            if not applied:
                path_action.declined = True
        elif plan.profile_path and plan.export_line:
            path_action.declined = True
        outcome.path_action = path_action
        outcome.code = InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP
        outcome.message = "dbgoracle installed, but PATH needs one more step."

    def _is_binary_discoverable(self, binary_path: str) -> bool:
        discovered = shutil.which(DEFAULT_BINARY_NAME, path=self.env.get("PATH"))
        if discovered:
            discovered_path = Path(discovered)
            target_path = Path(binary_path)
            try:
                return discovered_path.samefile(target_path)
            except OSError:
                return discovered_path.resolve() == target_path.resolve()
        return linux_platform.path_contains(Path(binary_path).parent, self.env.get("PATH"))

    def _verify_status_binary(self, status: InstallationStatus, expected_version: str) -> tuple[bool, str]:
        binary_path = status.binary_path or str(self.backend.bin_dir() / DEFAULT_BINARY_NAME)
        return self.backend.verify_cli(
            DEFAULT_BINARY_NAME,
            binary_path=binary_path,
            expected_version=expected_version,
        )


def create_default_installer(
    *,
    env: dict[str, str] | None = None,
    input_func: Callable[[str], str] | None = None,
) -> InstallerCore:
    runtime_env = dict(os.environ if env is None else env)
    return InstallerCore(
        backend=PipxBackend(env=runtime_env),
        fetcher=ManifestFetcher(),
        env=runtime_env,
        input_func=input_func,
    )


def _doctor_notes(env: dict[str, str]) -> list[str]:
    notes: list[str] = []
    if shutil.which("openocd", path=env.get("PATH")) is None:
        notes.append("Later workflow note: openocd is not on PATH yet. Install success is still valid; embedded capture checks happen later.")
    return notes


def _python_satisfies(version: tuple[int, int, int], specifier: str) -> bool:
    clauses = [piece.strip() for piece in specifier.split(",") if piece.strip()]
    for clause in clauses:
        operator = next((candidate for candidate in (">=", "<=", "==", ">", "<") if clause.startswith(candidate)), None)
        if operator is None:
            return False
        expected = tuple(int(part) for part in clause[len(operator) :].split("."))
        padded_version = version + (0,) * (len(expected) - len(version))
        if operator == ">=" and not (padded_version >= expected):
            return False
        if operator == ">" and not (padded_version > expected):
            return False
        if operator == "<=" and not (padded_version <= expected):
            return False
        if operator == "<" and not (padded_version < expected):
            return False
        if operator == "==" and not (padded_version == expected):
            return False
    return True


def _compare_versions(left: str, right: str) -> int:
    def normalize(raw: str) -> list[int]:
        values: list[int] = []
        for piece in raw.split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            values.append(int(digits or "0"))
        return values

    left_parts = normalize(left)
    right_parts = normalize(right)
    size = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (size - len(left_parts)))
    right_parts.extend([0] * (size - len(right_parts)))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0
