from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...installer.backend.pipx import PipxBackend, PipxError
from ...installer.outcomes import InstallState
from ...installer.platform import linux as linux_platform
from ...installer.platform import macos as macos_platform
from ...installer.platform import windows as windows_platform

PACKAGE_NAME = "debugoracle"
CLI_NAME = "dbgoracle"


@dataclass(slots=True)
class PathCleanupPayload:
    profile_path: str | None
    export_line: str | None
    applied: bool = False
    marker_found: bool = False
    legacy_line_found: bool = False
    skipped: bool = False
    force_legacy: bool = False
    error: str | None = None
    manual_action: str | None = None


@dataclass(slots=True)
class UninstallOutcome:
    code: str
    success: bool
    message: str
    details: list[str] = field(default_factory=list)
    path_cleanup: PathCleanupPayload | None = None


def _should_prompt_for_confirmation(args: Any) -> bool:
    return bool(args.format == "text" and sys.stdin.isatty())


def _confirm_uninstall() -> bool:
    answer = input(
        "Uninstall dbgoracle and bundled docs tooling (docling/semantic if installed)? [Y/n] "
    ).strip()
    return answer.lower() in {"", "y", "yes"}


def cmd_uninstall_cli(args: Any) -> int:
    if not sys.platform.startswith(("linux", "darwin", "win32")):
        return _emit_outcome(
            args,
            UninstallOutcome(
                code="blocked_platform",
                success=False,
                message="Installer support is available only on Linux, macOS, and Windows.",
                details=[f"Detected platform: {sys.platform}"],
            ),
        )

    backend = PipxBackend()
    if not backend.is_available():
        return _emit_outcome(
            args,
            UninstallOutcome(
                code="blocked_missing_pipx",
                success=False,
                message="pipx is required for uninstall.",
                details=["Install pipx first, then rerun uninstall."],
            ),
        )

    try:
        current = backend.inspect_installation(PACKAGE_NAME, "0")
    except PipxError as error:
        return _emit_outcome(
            args,
            UninstallOutcome(
                code="failed_uninstall",
                success=False,
                message="Unable to inspect the current pipx installation state.",
                details=[str(error)],
            ),
        )

    was_installed = current.state != InstallState.NOT_INSTALLED
    if was_installed:
        if _should_prompt_for_confirmation(args) and not _confirm_uninstall():
            return _emit_outcome(
                args,
                UninstallOutcome(
                    code="cancelled_by_user",
                    success=True,
                    message="Uninstall cancelled by user.",
                    details=["No changes were made."],
                ),
            )
        try:
            backend.uninstall(PACKAGE_NAME)
        except PipxError as error:
            return _emit_outcome(
                args,
                UninstallOutcome(
                    code="failed_uninstall",
                    success=False,
                    message="pipx could not complete the uninstall step.",
                    details=[str(error)],
                ),
            )

    message = (
        f"{CLI_NAME} removed successfully."
        if was_installed
        else f"{CLI_NAME} is not currently installed."
    )
    outcome = UninstallOutcome(
        code="success_uninstalled" if was_installed else "success_not_installed",
        success=True,
        message=message,
    )
    if was_installed:
        outcome.details.append(
            "Removed dbgoracle and bundled docs tooling from the pipx environment."
        )

    if args.keep_path:
        outcome.path_cleanup = PathCleanupPayload(
            profile_path=None,
            export_line=None,
            skipped=True,
            force_legacy=bool(args.force_legacy_path_cleanup),
        )
        outcome.details.append("Skipped PATH profile cleanup (--keep-path).")
        return _emit_outcome(args, outcome)

    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    platform_adapter = _platform_adapter()
    plan = platform_adapter.build_path_plan(
        backend.bin_dir(), os.environ.get("SHELL"), home, os.environ
    )
    profile_path = plan.profile_path
    export_line = plan.export_line
    cleanup_payload = PathCleanupPayload(
        profile_path=str(profile_path) if profile_path else None,
        export_line=export_line,
        force_legacy=bool(args.force_legacy_path_cleanup),
    )
    outcome.path_cleanup = cleanup_payload
    if profile_path is None or export_line is None:
        cleanup_payload.skipped = True
        outcome.details.append("No supported shell profile detected for PATH cleanup.")
        return _emit_outcome(args, outcome)

    cleanup = platform_adapter.cleanup_path_line(
        profile_path,
        export_line,
        force_legacy=bool(args.force_legacy_path_cleanup),
    )
    cleanup_payload.applied = cleanup.applied
    cleanup_payload.marker_found = cleanup.marker_found
    cleanup_payload.legacy_line_found = cleanup.legacy_line_found
    cleanup_payload.error = cleanup.error
    cleanup_payload.manual_action = cleanup.manual_action
    if cleanup.error:
        outcome.code = "failed_profile_cleanup"
        outcome.success = False
        outcome.message = "Uninstall completed, but profile cleanup failed."
        outcome.details.append(cleanup.error)
        return _emit_outcome(args, outcome)
    if cleanup.manual_action:
        outcome.details.append(cleanup.manual_action)
    return _emit_outcome(args, outcome)


def _emit_outcome(args: Any, outcome: UninstallOutcome) -> int:
    if args.format == "json":
        payload = {
            "code": outcome.code,
            "success": outcome.success,
            "message": outcome.message,
            "details": outcome.details,
            "path_cleanup": None
            if outcome.path_cleanup is None
            else {
                "profile_path": outcome.path_cleanup.profile_path,
                "export_line": outcome.path_cleanup.export_line,
                "applied": outcome.path_cleanup.applied,
                "marker_found": outcome.path_cleanup.marker_found,
                "legacy_line_found": outcome.path_cleanup.legacy_line_found,
                "skipped": outcome.path_cleanup.skipped,
                "force_legacy": outcome.path_cleanup.force_legacy,
                "error": outcome.path_cleanup.error,
                "manual_action": outcome.path_cleanup.manual_action,
            },
        }
        print(json.dumps(payload, indent=2))
    else:
        stream = sys.stdout if outcome.success else sys.stderr
        print(outcome.message, file=stream)
        for detail in outcome.details:
            print(f"- {detail}", file=stream)
        if outcome.path_cleanup is not None:
            if outcome.path_cleanup.profile_path:
                print(f"Profile file: {outcome.path_cleanup.profile_path}", file=stream)
            if outcome.path_cleanup.export_line:
                print(f"PATH line: {outcome.path_cleanup.export_line}", file=stream)
            if outcome.path_cleanup.skipped:
                print("PATH cleanup skipped.", file=stream)
            elif outcome.path_cleanup.applied:
                print("PATH cleanup applied.", file=stream)
            elif outcome.path_cleanup.manual_action:
                print("PATH cleanup requires manual action.", file=stream)
            if outcome.path_cleanup.error:
                print(
                    f"Profile cleanup error: {outcome.path_cleanup.error}", file=stream
                )
    return 0 if outcome.success else 1


def _platform_adapter():
    if sys.platform.startswith("win32"):
        return windows_platform
    if sys.platform.startswith("darwin"):
        return macos_platform
    return linux_platform
