#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "release" / "install-manifest.json"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from debugoracle.cli.main import main  # noqa: E402


DOCS_MODE_NONE = "none"
DOCS_MODE_DOCLING = "docling"
DOCS_MODE_SEMANTIC = "semantic"
DOCS_MODE_ALL = "all"
DOCS_MODE_PROMPT = "prompt"


def _parse_bootstrap_args(argv: list[str]) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--docs-tools",
        choices=[
            DOCS_MODE_PROMPT,
            DOCS_MODE_NONE,
            DOCS_MODE_DOCLING,
            DOCS_MODE_SEMANTIC,
            DOCS_MODE_ALL,
        ],
        default=DOCS_MODE_PROMPT,
        help=argparse.SUPPRESS,
    )
    known, passthrough = parser.parse_known_args(argv)
    return str(known.docs_tools), passthrough


def _render_docs_tools_intro() -> None:
    print("Optional docs tooling can improve manual/datasheet ingest quality.")
    print(
        "  - docling: better extraction on hard or scanned PDFs (heavier dependency)."
    )
    print(
        "  - semantic: hybrid semantic search over ingested docs (installs embedding deps)."
    )


def _ask_docs_tools_choice() -> str:
    print()
    _render_docs_tools_intro()
    print("Choose optional docs tooling:")
    print("  [1] Skip for now (fastest setup)")
    print("  [2] Install docling only")
    print("  [3] Install semantic search only")
    print("  [4] Install both docling + semantic search")
    selected = input("Selection [1-4, default 1]: ").strip()
    mapping = {
        "1": DOCS_MODE_NONE,
        "2": DOCS_MODE_DOCLING,
        "3": DOCS_MODE_SEMANTIC,
        "4": DOCS_MODE_ALL,
    }
    return mapping.get(selected, DOCS_MODE_NONE)


def _inject_requirements(requirements: list[str]) -> bool:
    command = ["pipx", "inject", "debugoracle", *requirements]
    result = subprocess.run(command, check=False)
    return result.returncode == 0


def _handle_optional_install_failure(remediation: str) -> int:
    print("Optional docs tooling installation failed.", file=sys.stderr)
    print(f"Remediation: {remediation}", file=sys.stderr)
    if not sys.stdin.isatty():
        print(
            "Non-interactive mode: failing setup due to optional tooling install failure.",
            file=sys.stderr,
        )
        return 1

    answer = input("Continue with base dbgoracle install only? [Y/n] ").strip().lower()
    if answer in {"", "y", "yes"}:
        print("Continuing with base dbgoracle install only.")
        return 0
    print("Aborting setup due to optional tooling install failure.", file=sys.stderr)
    return 1


def _install_docs_tools(selection: str) -> int:
    if selection == DOCS_MODE_NONE:
        print("Skipped optional docs tooling setup.")
        print(
            "Install later with: pipx inject debugoracle docling sentence-transformers numpy"
        )
        return 0

    print()
    _render_docs_tools_intro()
    print("Installing selected docs tooling...")

    if selection == DOCS_MODE_DOCLING:
        if _inject_requirements(["docling"]):
            print("Installed docling support.")
            return 0
        return _handle_optional_install_failure("pipx inject debugoracle docling")

    if selection == DOCS_MODE_SEMANTIC:
        if _inject_requirements(["sentence-transformers", "numpy"]):
            print("Installed semantic search dependencies.")
            return 0
        return _handle_optional_install_failure(
            "pipx inject debugoracle sentence-transformers numpy"
        )

    if selection == DOCS_MODE_ALL:
        if _inject_requirements(["docling", "sentence-transformers", "numpy"]):
            print("Installed docling + semantic search dependencies.")
            return 0
        return _handle_optional_install_failure(
            "pipx inject debugoracle docling sentence-transformers numpy"
        )

    print(f"Unknown docs-tools selection: {selection}", file=sys.stderr)
    return 1


def bootstrap(argv: list[str] | None = None) -> int:
    raw_args = list(argv or sys.argv[1:])
    docs_tools_mode, passthrough = _parse_bootstrap_args(raw_args)
    install_code = main(
        [
            "install-cli",
            "--manifest-url",
            str(MANIFEST_PATH),
            *passthrough,
        ]
    )
    if install_code != 0:
        return install_code

    selected_mode = docs_tools_mode
    if docs_tools_mode == DOCS_MODE_PROMPT:
        if sys.stdin.isatty():
            selected_mode = _ask_docs_tools_choice()
        else:
            selected_mode = DOCS_MODE_NONE
            print(
                "Skipping optional docs tooling prompt because stdin is non-interactive."
            )
            print(
                "Install later with: pipx inject debugoracle docling sentence-transformers numpy"
            )
    return _install_docs_tools(selected_mode)


if __name__ == "__main__":
    raise SystemExit(bootstrap())
