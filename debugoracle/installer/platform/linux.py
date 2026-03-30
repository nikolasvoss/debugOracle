from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PATH_MARKER = "# debugoracle-managed-path"


@dataclass(slots=True)
class LinuxPathPlan:
    bin_dir: Path
    profile_path: Path | None
    export_line: str | None


@dataclass(slots=True)
class PathCleanupResult:
    applied: bool
    marker_found: bool
    legacy_line_found: bool
    manual_action: str | None = None
    error: str | None = None


def detect_profile_path(shell: str | None, home: Path, env: Mapping[str, str] | None = None) -> Path | None:
    env = env or os.environ
    shell_name = Path(shell or env.get("SHELL", "")).name
    if shell_name == "bash":
        return home / ".bashrc"
    if shell_name == "zsh":
        return home / ".zshrc"
    if shell_name == "fish":
        config_home = Path(env.get("XDG_CONFIG_HOME", home / ".config"))
        return config_home / "fish" / "config.fish"
    return None


def build_path_plan(bin_dir: Path, shell: str | None, home: Path, env: Mapping[str, str] | None = None) -> LinuxPathPlan:
    profile_path = detect_profile_path(shell, home, env)
    shell_name = Path(shell or (env or os.environ).get("SHELL", "")).name
    if shell_name == "fish":
        export_line = f"set -gx PATH {bin_dir} $PATH"
    else:
        export_line = f'export PATH="{bin_dir}:$PATH"'
    return LinuxPathPlan(bin_dir=bin_dir, profile_path=profile_path, export_line=export_line)


def path_contains(bin_dir: Path, path_value: str | None) -> bool:
    if not path_value:
        return False
    target = str(bin_dir)
    return any(segment == target for segment in path_value.split(os.pathsep) if segment)


def append_path_line(profile_path: Path, export_line: str) -> tuple[bool, str | None]:
    try:
        existing = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
        if _has_managed_block(existing, export_line) or _has_exact_path_line(existing, export_line):
            return True, None
        if profile_path.parent and not profile_path.parent.exists():
            profile_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if existing.endswith("\n") or not existing else "\n"
        profile_path.write_text(
            f"{existing}{prefix}{PATH_MARKER}\n{export_line}\n",
            encoding="utf-8",
        )
        return True, None
    except OSError as error:
        return False, str(error)


def cleanup_path_line(
    profile_path: Path,
    export_line: str,
    *,
    force_legacy: bool = False,
) -> PathCleanupResult:
    try:
        if not profile_path.exists():
            return PathCleanupResult(
                applied=False,
                marker_found=False,
                legacy_line_found=False,
            )
        existing = profile_path.read_text(encoding="utf-8")
        original_had_trailing_newline = existing.endswith("\n")
        lines = existing.splitlines()
        updated_lines: list[str] = []
        marker_found = False
        legacy_line_found = False
        marker_line_requires_manual_action = False
        applied = False
        managed_bin_dir = _extract_bin_dir_from_export_line(export_line)
        index = 0
        while index < len(lines):
            current = lines[index]
            if current.strip() == PATH_MARKER:
                marker_found = True
                applied = True
                if index + 1 >= len(lines):
                    index += 1
                    continue
                next_line = lines[index + 1]
                if _line_matches_path_export(next_line, export_line, managed_bin_dir):
                    index += 2
                    continue
                marker_line_requires_manual_action = True
                updated_lines.append(next_line)
                index += 2
                continue
            if _line_matches_path_export(current, export_line, managed_bin_dir):
                legacy_line_found = True
                if force_legacy:
                    applied = True
                    index += 1
                    continue
            updated_lines.append(current)
            index += 1
        if applied:
            rebuilt = "\n".join(updated_lines)
            if rebuilt and original_had_trailing_newline:
                rebuilt += "\n"
            profile_path.write_text(rebuilt, encoding="utf-8")
        manual_action = None
        if marker_line_requires_manual_action:
            manual_action = (
                f"Installer marker removed from {profile_path}, but the following PATH line "
                "is non-standard and was left unchanged. Verify the PATH entry manually."
            )
        if legacy_line_found and not force_legacy and not marker_found:
            escaped_line = export_line.replace("'", "'\"'\"'")
            manual_action = (
                f"Legacy PATH line left untouched. Remove this line from {profile_path}: "
                f"{escaped_line}"
            )
        return PathCleanupResult(
            applied=applied,
            marker_found=marker_found,
            legacy_line_found=legacy_line_found,
            manual_action=manual_action,
        )
    except OSError as error:
        return PathCleanupResult(
            applied=False,
            marker_found=False,
            legacy_line_found=False,
            error=str(error),
        )


def _has_exact_path_line(existing: str, export_line: str) -> bool:
    return any(line.strip() == export_line for line in existing.splitlines())


def _has_managed_block(existing: str, export_line: str) -> bool:
    lines = existing.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != PATH_MARKER:
            continue
        if index + 1 < len(lines) and lines[index + 1].strip() == export_line:
            return True
    return False


def _extract_bin_dir_from_export_line(export_line: str) -> str | None:
    bash_prefix = 'export PATH="'
    bash_suffix = ':$PATH"'
    fish_prefix = "set -gx PATH "
    fish_suffix = " $PATH"
    if export_line.startswith(bash_prefix) and export_line.endswith(bash_suffix):
        return export_line[len(bash_prefix) : -len(bash_suffix)]
    if export_line.startswith(fish_prefix) and export_line.endswith(fish_suffix):
        return export_line[len(fish_prefix) : -len(fish_suffix)]
    return None


def _line_matches_path_export(line: str, export_line: str, managed_bin_dir: str | None) -> bool:
    stripped = line.strip()
    if stripped == export_line:
        return True
    if managed_bin_dir is None or not stripped:
        return False
    if stripped.startswith("#"):
        return False
    return managed_bin_dir in stripped and "$PATH" in stripped
