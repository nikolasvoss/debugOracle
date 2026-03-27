from __future__ import annotations

import importlib.util
import shlex
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticCheck:
    key: str
    required: bool
    ready: bool
    detail: str
    remedy: str = ""


def is_command_available(command: str, *, env: dict[str, str] | None = None) -> bool:
    path = None if env is None else env.get("PATH")
    return shutil.which(command, path=path) is not None


def build_installer_doctor_notes(env: dict[str, str]) -> list[str]:
    notes: list[str] = []
    if not is_command_available("openocd", env=env):
        notes.append(
            "Later workflow note: openocd is not on PATH yet. Install success is still valid; embedded capture checks happen later."
        )
    return notes


def collect_docs_doctor_checks(
    *,
    python_executable: str | None = None,
) -> list[DiagnosticCheck]:
    executable = python_executable or sys.executable
    quoted_executable = shlex.quote(executable)
    checks: list[DiagnosticCheck] = []

    checks.append(
        _module_check(
            key="pymupdf",
            required=True,
            remedy=f"{quoted_executable} -m pip install pymupdf",
        )
    )
    checks.append(
        _module_check(
            key="pymupdf4llm",
            required=True,
            remedy=f"{quoted_executable} -m pip install pymupdf4llm",
        )
    )
    checks.append(
        _module_check(
            key="docling",
            required=False,
            remedy=(
                "pipx inject debugoracle docling\n"
                f"  or: {quoted_executable} -m pip install 'debugoracle[docling]'"
            ),
        )
    )

    semantic_numpy = _module_check(
        key="numpy",
        required=False,
        remedy=(
            "pipx inject debugoracle sentence-transformers numpy\n"
            f"  or: {quoted_executable} -m pip install 'debugoracle[semantic]'"
        ),
    )
    semantic_st = _module_check(
        key="sentence_transformers",
        required=False,
        remedy=(
            "pipx inject debugoracle sentence-transformers numpy\n"
            f"  or: {quoted_executable} -m pip install 'debugoracle[semantic]'"
        ),
    )
    checks.extend([semantic_numpy, semantic_st])
    return checks


def _module_check(*, key: str, required: bool, remedy: str) -> DiagnosticCheck:
    available = importlib.util.find_spec(key) is not None
    detail = "installed" if available else "missing"
    return DiagnosticCheck(
        key=key,
        required=required,
        ready=available,
        detail=detail,
        remedy=remedy if not available else "",
    )
