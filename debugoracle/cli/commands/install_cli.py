from __future__ import annotations

import json
import sys
from typing import Any

from ...installer import InstallerOptions, create_default_installer


def cmd_install_cli(args: Any) -> int:
    installer = create_default_installer()
    outcome = installer.run(
        InstallerOptions(
            manifest_url=args.manifest_url or None,
            channel=args.channel,
            package_source_override=args.package_source,
            assume_yes=args.yes,
            doctor=not args.no_doctor,
        )
    )
    if args.format == "json":
        payload = {
            "code": outcome.code.value,
            "success": outcome.success,
            "message": outcome.message,
            "version": outcome.version,
            "installed_version": outcome.installed_version,
            "details": outcome.details,
            "doctor_notes": outcome.doctor_notes,
            "path_action": None
            if outcome.path_action is None
            else {
                "bin_dir": outcome.path_action.bin_dir,
                "profile_path": outcome.path_action.profile_path,
                "export_line": outcome.path_action.export_line,
                "applied": outcome.path_action.applied,
                "declined": outcome.path_action.declined,
                "error": outcome.path_action.error,
            },
        }
        print(json.dumps(payload, indent=2))
    else:
        stream = sys.stdout if outcome.success else sys.stderr
        print(outcome.message, file=stream)
        if outcome.version:
            print(f"Target version: {outcome.version}", file=stream)
        if outcome.installed_version:
            print(f"Installed version: {outcome.installed_version}", file=stream)
        for detail in outcome.details:
            print(f"- {detail}", file=stream)
        if outcome.path_action is not None:
            print(f"PATH directory: {outcome.path_action.bin_dir}", file=stream)
            if outcome.path_action.profile_path:
                print(f"Profile file: {outcome.path_action.profile_path}", file=stream)
            if outcome.path_action.export_line:
                print(
                    f"Add this line if needed: {outcome.path_action.export_line}",
                    file=stream,
                )
            if outcome.path_action.error:
                print(f"Profile update error: {outcome.path_action.error}", file=stream)
        if outcome.doctor_notes:
            print("Doctor notes:", file=stream)
            for note in outcome.doctor_notes:
                print(f"- {note}", file=stream)
    return 0 if outcome.success else 1
