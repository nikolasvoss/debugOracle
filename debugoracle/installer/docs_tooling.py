from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from typing import Callable

DOCS_MODE_NONE = "none"
DOCS_MODE_DOCLING = "docling"
DOCS_MODE_SEMANTIC = "semantic"
DOCS_MODE_ALL = "all"
DOCS_MODE_PROMPT = "prompt"

REMEDIATION_INSTALL_FIRST = "Run ./scripts/install/linux.sh first."
REMEDIATION_INSTALL_PIPX = "Install pipx first, then retry."

_SELECTION_REQUIREMENTS: dict[str, list[str]] = {
    DOCS_MODE_NONE: [],
    DOCS_MODE_DOCLING: ["docling"],
    DOCS_MODE_SEMANTIC: ["sentence-transformers", "numpy"],
    DOCS_MODE_ALL: ["docling", "sentence-transformers", "numpy"],
}


@dataclass(slots=True)
class DocsToolingOutcome:
    code: str
    success: bool
    message: str
    selection: str
    requirements: list[str]
    remediation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "success": self.success,
            "message": self.message,
            "selection": self.selection,
            "requirements": self.requirements,
            "remediation": self.remediation,
        }


def remediation_for_selection(selection: str) -> str:
    requirements = _SELECTION_REQUIREMENTS.get(selection, [])
    if not requirements:
        return "pipx inject debugoracle docling sentence-transformers numpy"
    return f"pipx inject debugoracle {' '.join(requirements)}"


def install_docs_tooling(
    selection: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    which: Callable[..., str | None] = shutil.which,
    env: dict[str, str] | None = None,
) -> DocsToolingOutcome:
    resolved_env = dict(os.environ if env is None else env)
    requirements = list(_SELECTION_REQUIREMENTS.get(selection, []))
    remediation = remediation_for_selection(selection)

    if selection not in _SELECTION_REQUIREMENTS:
        return DocsToolingOutcome(
            code="failed_invalid_selection",
            success=False,
            message=f"Unknown docs-tools selection: {selection}",
            selection=selection,
            requirements=[],
            remediation="Use one of: none, docling, semantic, all.",
        )

    if selection == DOCS_MODE_NONE:
        return DocsToolingOutcome(
            code="success_skipped",
            success=True,
            message="Skipped optional docs tooling setup.",
            selection=selection,
            requirements=requirements,
            remediation=remediation,
        )

    pipx = which("pipx", path=resolved_env.get("PATH"))
    if pipx is None:
        return DocsToolingOutcome(
            code="blocked_missing_pipx",
            success=False,
            message="pipx is required to install optional docs tooling.",
            selection=selection,
            requirements=requirements,
            remediation=REMEDIATION_INSTALL_PIPX,
        )

    state = runner(  # nosec B603
        ["pipx", "list", "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=resolved_env,
    )
    if state.returncode != 0:
        message = (
            state.stderr or state.stdout or "Unable to inspect pipx installation state."
        ).strip()
        return DocsToolingOutcome(
            code="failed_pipx_state",
            success=False,
            message=message,
            selection=selection,
            requirements=requirements,
            remediation=REMEDIATION_INSTALL_FIRST,
        )
    try:
        payload = json.loads(state.stdout or "{}")
    except json.JSONDecodeError:
        return DocsToolingOutcome(
            code="failed_pipx_state",
            success=False,
            message="Unable to parse pipx installation state.",
            selection=selection,
            requirements=requirements,
            remediation=REMEDIATION_INSTALL_FIRST,
        )
    venvs = payload.get("venvs") if isinstance(payload, dict) else None
    if not isinstance(venvs, dict) or "debugoracle" not in venvs:
        return DocsToolingOutcome(
            code="blocked_missing_debugoracle",
            success=False,
            message="debugoracle is not installed in pipx.",
            selection=selection,
            requirements=requirements,
            remediation=REMEDIATION_INSTALL_FIRST,
        )

    completed = runner(  # nosec B603
        ["pipx", "inject", "debugoracle", *requirements],
        check=False,
        capture_output=True,
        text=True,
        env=resolved_env,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "pipx inject failed").strip()
        return DocsToolingOutcome(
            code="failed_inject",
            success=False,
            message=message,
            selection=selection,
            requirements=requirements,
            remediation=remediation,
        )

    success_message = {
        DOCS_MODE_DOCLING: "Installed docling support.",
        DOCS_MODE_SEMANTIC: "Installed semantic search dependencies.",
        DOCS_MODE_ALL: "Installed docling + semantic search dependencies.",
    }[selection]
    return DocsToolingOutcome(
        code="success_installed",
        success=True,
        message=success_message,
        selection=selection,
        requirements=requirements,
        remediation=remediation,
    )
