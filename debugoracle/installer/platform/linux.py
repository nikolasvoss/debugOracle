from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class LinuxPathPlan:
    bin_dir: Path
    profile_path: Path | None
    export_line: str | None


def detect_profile_path(shell: str | None, home: Path, env: dict[str, str] | None = None) -> Path | None:
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


def build_path_plan(bin_dir: Path, shell: str | None, home: Path, env: dict[str, str] | None = None) -> LinuxPathPlan:
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
        if export_line in existing:
            return True, None
        if profile_path.parent and not profile_path.parent.exists():
            profile_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if existing.endswith("\n") or not existing else "\n"
        profile_path.write_text(f"{existing}{prefix}{export_line}\n", encoding="utf-8")
        return True, None
    except OSError as error:
        return False, str(error)
