from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InstallState(str, Enum):
    NOT_INSTALLED = "not_installed"
    INSTALLED_SAME_VERSION = "installed_same_version"
    INSTALLED_OLDER_VERSION = "installed_older_version"
    INSTALLED_NEWER_VERSION = "installed_newer_version"
    INSTALL_IN_PROGRESS = "install_in_progress"


class InstallerOutcomeCode(str, Enum):
    SUCCESS_INSTALLED = "success_installed"
    SUCCESS_UPGRADED = "success_upgraded"
    SUCCESS_ALREADY_INSTALLED = "success_already_installed"
    SUCCESS_NEEDS_PATH_STEP = "success_needs_path_step"
    BLOCKED_PLATFORM = "blocked_platform"
    BLOCKED_MISSING_PYTHON = "blocked_missing_python"
    BLOCKED_MISSING_PIPX = "blocked_missing_pipx"
    BLOCKED_MANIFEST = "blocked_manifest"
    FAILED_NETWORK_TRANSIENT = "failed_network_transient"
    FAILED_ARTIFACT = "failed_artifact"
    FAILED_INSTALL = "failed_install"
    FAILED_POST_INSTALL_INSPECTION = "failed_post_install_inspection"
    FAILED_VERIFY = "failed_verify"
    FAILED_CLEANUP = "failed_cleanup"
    UNKNOWN_INTERNAL_ERROR = "unknown_internal_error"


@dataclass(slots=True)
class PathAction:
    bin_dir: str
    profile_path: str | None
    export_line: str | None
    applied: bool = False
    declined: bool = False
    error: str | None = None
    needs_current_shell_step: bool = True


@dataclass(slots=True)
class InstallerOutcome:
    code: InstallerOutcomeCode
    message: str
    version: str | None = None
    installed_version: str | None = None
    details: list[str] = field(default_factory=list)
    doctor_notes: list[str] = field(default_factory=list)
    path_action: PathAction | None = None

    @property
    def success(self) -> bool:
        return self.code in {
            InstallerOutcomeCode.SUCCESS_INSTALLED,
            InstallerOutcomeCode.SUCCESS_UPGRADED,
            InstallerOutcomeCode.SUCCESS_ALREADY_INSTALLED,
            InstallerOutcomeCode.SUCCESS_NEEDS_PATH_STEP,
        }
