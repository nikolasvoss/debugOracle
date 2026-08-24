from __future__ import annotations

import os
import shutil
import sys
import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlparse

from ..diagnostics import build_installer_doctor_notes
from .backend.pipx import InstallationStatus, PipxBackend, PipxError
from .manifest import (
    ManifestError,
    ManifestFetcher,
    ManifestNetworkError,
    ReleaseManifest,
)
from .outcomes import InstallState, InstallerOutcome, InstallerOutcomeCode, PathAction
from .platform import linux as linux_platform
from .source import (
    ArtifactDownloader,
    ArtifactError,
    ArtifactNetworkError,
    ArtifactSource,
)
from .versioning import VersioningError, compare_versions, satisfies

INSTALLER_VERSION = "0.2.0"
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/nikolasvoss/debugOracle/main/release/install-manifest.json"
DEFAULT_BINARY_NAME = "dbgoracle"


@dataclass(slots=True)
class InstallerOptions:
    manifest_url: str | None = DEFAULT_MANIFEST_URL
    channel: str = "stable"
    package_source_override: str | None = None
    assume_yes: bool = False
    doctor: bool = True


class InstallerBackend(Protocol):
    def is_available(self) -> bool: ...

    def bin_dir(self) -> Path: ...

    def inspect_installation(
        self, package_name: str, target_version: str
    ) -> InstallationStatus: ...

    def install(self, source_spec: str, *, force: bool = False) -> None: ...

    def upgrade(self, package_name: str, source_spec: str | None = None) -> None: ...

    def uninstall(self, package_name: str) -> None: ...

    def verify_cli(
        self,
        binary_name: str,
        *,
        binary_path: str | None = None,
        expected_version: str | None = None,
    ) -> tuple[bool, str]: ...


class ManifestSource(Protocol):
    def fetch(self, manifest_url: str) -> ReleaseManifest: ...


class InstallerCore:
    def __init__(
        self,
        *,
        backend: InstallerBackend,
        fetcher: ManifestSource,
        downloader: ArtifactSource | None = None,
        env: dict[str, str] | None = None,
        python_version: tuple[int, int, int] | None = None,
        sleep: Callable[[float], None] | None = None,
        input_func: Callable[[str], str] | None = None,
    ) -> None:
        self.backend = backend
        self.fetcher = fetcher
        self.downloader = downloader or ArtifactDownloader()
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
                details=[
                    f"Detected Python: {'.'.join(str(part) for part in self.python_version)}"
                ],
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
        python_version = ".".join(str(part) for part in self.python_version)
        try:
            python_supported = satisfies(python_version, manifest.python_requires)
            installer_supported = (
                compare_versions(INSTALLER_VERSION, manifest.installer_min_version) >= 0
            )
        except VersioningError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MANIFEST,
                message="The installer manifest contains invalid version policy.",
                details=[str(error)],
            )
        if not python_supported:
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MISSING_PYTHON,
                message="Your Python version does not satisfy the release requirements.",
                details=[
                    f"Detected Python: {'.'.join(str(part) for part in self.python_version)}",
                    f"Required: {manifest.python_requires}",
                ],
            )
        if not installer_supported:
            return InstallerOutcome(
                code=InstallerOutcomeCode.BLOCKED_MANIFEST,
                message="This installer is older than the minimum supported installer version.",
                details=[
                    f"Installer version: {INSTALLER_VERSION}",
                    f"Required installer version: {manifest.installer_min_version}",
                ],
            )

        try:
            current = self.backend.inspect_installation(
                manifest.package_name, manifest.version
            )
        except PipxError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.FAILED_INSTALL,
                message="Unable to inspect the current pipx installation state.",
                details=[str(error)],
            )

        if current.state in {
            InstallState.INSTALLED_SAME_VERSION,
            InstallState.INSTALLED_NEWER_VERSION,
        }:
            verified, verify_message = self._verify_status_binary(
                current, current.installed_version or manifest.version
            )
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

        if options.package_source_override is not None:
            try:
                local_source = _resolve_local_source(options.package_source_override)
            except ArtifactError as error:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_ARTIFACT,
                    message="The package source override must be a local checkout path.",
                    version=manifest.version,
                    details=[str(error)],
                )
            outcome = self._install_source(
                manifest, current, str(local_source), options
            )
            outcome.details.append(
                f"Package source: explicit local checkout {local_source}"
            )
            return outcome
        try:
            with tempfile.TemporaryDirectory(prefix="debugoracle-installer-") as tmpdir:
                source_path = self.downloader.download(manifest, Path(tmpdir))
                return self._install_source(
                    manifest, current, str(source_path), options
                )
        except ArtifactError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.FAILED_ARTIFACT,
                message="The release artifact failed integrity validation.",
                version=manifest.version,
                details=[str(error)],
            )
        except ArtifactNetworkError as error:
            return InstallerOutcome(
                code=InstallerOutcomeCode.FAILED_NETWORK_TRANSIENT,
                message="Unable to download the verified release artifact.",
                version=manifest.version,
                details=[str(error)],
            )

    def _install_source(
        self,
        manifest: ReleaseManifest,
        current: InstallationStatus,
        source_spec: str,
        options: InstallerOptions,
    ) -> InstallerOutcome:
        try:
            if current.state == InstallState.INSTALLED_OLDER_VERSION:
                self.backend.upgrade(manifest.package_name, source_spec)
                action = InstallerOutcomeCode.SUCCESS_UPGRADED
                success_message = f"dbgoracle upgraded to {manifest.version}."
            else:
                self.backend.install(source_spec)
                action = InstallerOutcomeCode.SUCCESS_INSTALLED
                success_message = (
                    f"dbgoracle {manifest.version} installed successfully."
                )
        except PipxError as error:
            return self._handle_install_failure(error, manifest, current)

        try:
            post_install = self.backend.inspect_installation(
                manifest.package_name, manifest.version
            )
        except PipxError as error:
            return self._handle_post_install_inspection_failure(
                manifest, current, error
            )
        verified, verify_message = self._verify_status_binary(
            post_install, manifest.version
        )
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

    def _handle_post_install_inspection_failure(
        self,
        manifest: ReleaseManifest,
        current: InstallationStatus,
        error: PipxError,
    ) -> InstallerOutcome:
        details = [
            str(error),
            "Run 'pipx list --json' and 'dbgoracle --version' before retrying.",
        ]
        if current.state == InstallState.NOT_INSTALLED:
            try:
                self.backend.uninstall(manifest.package_name)
            except PipxError as cleanup_error:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="Post-install inspection failed and cleanup could not restore a clean state.",
                    version=manifest.version,
                    details=[*details, str(cleanup_error)],
                )
        return InstallerOutcome(
            code=InstallerOutcomeCode.FAILED_POST_INSTALL_INSPECTION,
            message="pipx changed the installation, but its resulting state could not be inspected.",
            version=manifest.version,
            installed_version=current.installed_version,
            details=details,
        )

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
                restored = self.backend.inspect_installation(
                    manifest.package_name, current.installed_version or "0"
                )
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
            try:
                restored = self.backend.inspect_installation(
                    manifest.package_name, current.installed_version or "0"
                )
            except PipxError as inspect_error:
                return InstallerOutcome(
                    code=InstallerOutcomeCode.FAILED_CLEANUP,
                    message="CLI verification failed and the previous installation could not be inspected.",
                    version=manifest.version,
                    details=[verify_message, str(inspect_error)],
                )
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
            outcome.doctor_notes.extend(build_installer_doctor_notes(self.env))
        binary_path = status.binary_path or str(
            self.backend.bin_dir() / DEFAULT_BINARY_NAME
        )
        binary_dir = Path(binary_path).parent
        if self._is_binary_discoverable(binary_path):
            return
        home = Path(self.env.get("HOME", str(Path.home()))).expanduser()
        plan = linux_platform.build_path_plan(
            binary_dir, self.env.get("SHELL"), home, self.env
        )
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
            applied, error = linux_platform.append_path_line(
                plan.profile_path, plan.export_line
            )
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
        return linux_platform.path_contains(
            Path(binary_path).parent, self.env.get("PATH")
        )

    def _verify_status_binary(
        self, status: InstallationStatus, expected_version: str
    ) -> tuple[bool, str]:
        binary_path = status.binary_path or str(
            self.backend.bin_dir() / DEFAULT_BINARY_NAME
        )
        try:
            return self.backend.verify_cli(
                DEFAULT_BINARY_NAME,
                binary_path=binary_path,
                expected_version=expected_version,
            )
        except (PipxError, OSError) as error:
            return False, f"Unable to run post-install CLI verification: {error}"


def create_default_installer(
    *,
    env: dict[str, str] | None = None,
    input_func: Callable[[str], str] | None = None,
) -> InstallerCore:
    runtime_env = dict(os.environ if env is None else env)
    return InstallerCore(
        backend=PipxBackend(env=runtime_env),
        fetcher=ManifestFetcher(),
        downloader=ArtifactDownloader(),
        env=runtime_env,
        input_func=input_func,
    )


def _resolve_local_source(raw_source: str) -> Path:
    if urlparse(raw_source).scheme:
        raise ArtifactError("Remote package source overrides are not permitted.")
    try:
        source = Path(raw_source).expanduser().resolve(strict=True)
    except OSError as error:
        raise ArtifactError(
            f"Local package source does not exist or cannot be resolved: {raw_source}"
        ) from error
    if not source.is_dir():
        raise ArtifactError(
            "Local package source override must be a checkout directory."
        )
    return source
