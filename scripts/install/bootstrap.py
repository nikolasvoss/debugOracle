#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "release" / "install-manifest.json"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from debugoracle.cli.main import main  # noqa: E402
from debugoracle.installer.docs_tooling import (  # noqa: E402
    DOCS_MODE_ALL,
    DOCS_MODE_DOCLING,
    DOCS_MODE_NONE,
    DOCS_MODE_PROMPT,
    DOCS_MODE_SEMANTIC,
    DocsToolingOutcome,
    install_docs_tooling,
)


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
    if selection != DOCS_MODE_NONE:
        print()
        _render_docs_tools_intro()
        print("Installing selected docs tooling...")

    outcome: DocsToolingOutcome = install_docs_tooling(selection)
    if outcome.success:
        print(outcome.message)
        if selection == DOCS_MODE_NONE:
            print("Install later with: ./scripts/install/linux.sh --docs-tools all")
        return 0

    return _handle_optional_install_failure(outcome.remediation)


def _sanitize_install_passthrough(args: list[str]) -> list[str]:
    sanitized: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--package-source":
            index += 2
            continue
        if token.startswith("--package-source="):
            index += 1
            continue
        sanitized.append(token)
        index += 1
    return sanitized


def _build_install_cli_args(passthrough: list[str]) -> list[str]:
    safe_passthrough = _sanitize_install_passthrough(passthrough)
    return [
        "install-cli",
        "--manifest-url",
        str(MANIFEST_PATH),
        "--package-source",
        str(REPO_ROOT),
        *safe_passthrough,
    ]


def bootstrap(argv: list[str] | None = None) -> int:
    raw_args = list(argv or sys.argv[1:])
    docs_tools_mode, passthrough = _parse_bootstrap_args(raw_args)
    install_code = main(_build_install_cli_args(passthrough))
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
            print("Install later with: ./scripts/install/linux.sh --docs-tools all")
    return _install_docs_tools(selected_mode)


if __name__ == "__main__":
    raise SystemExit(bootstrap())
