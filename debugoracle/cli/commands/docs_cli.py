from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from typing import Any

from ...diagnostics import collect_docs_doctor_checks
from ...docs_sidecar import (
    DocsIngestBatch,
    DocsIngestResult,
    ProgressCallback,
    DocsSearchResult,
    DocsStatusEntry,
    ingest_documents,
    search_documents,
    status_documents,
)
from .status_capture import emit


def cmd_docs_ingest(args: argparse.Namespace) -> int:
    progress_cb = _make_progress_cb(enabled=(args.format == "text" and not args.output))
    batch = _run_docs_ingest(args, progress_cb=progress_cb)
    output = _render_ingest(batch, fmt=args.format)
    exit_code = _ingest_exit_code(batch)
    emit(output, args.output)
    return exit_code


def cmd_docs_search(args: argparse.Namespace) -> int:
    result = search_documents(
        workspace_root=args.workspace_root,
        query=args.query,
        limit=args.limit,
        files=args.file,
        semantic=args.semantic,
    )
    output = _render_search(result, fmt=args.format)
    emit(output, args.output)
    if result.hits:
        return 0
    return 2 if result.warnings else 1


def cmd_docs_status(args: argparse.Namespace) -> int:
    statuses = status_documents(
        workspace_root=args.workspace_root,
        files=args.file,
    )
    output = _render_status(statuses, fmt=args.format)
    emit(output, args.output)
    if not statuses:
        return 1
    return 1 if any(item.ingest_state == "failed" for item in statuses) else 0


def cmd_docs_doctor(args: argparse.Namespace) -> int:
    checks = collect_docs_doctor_checks()
    payload: dict[str, Any] = {
        "checks": [
            {
                "name": check.key,
                "required": check.required,
                "ready": check.ready,
                "detail": check.detail,
                "remedy": check.remedy,
            }
            for check in checks
        ]
    }
    required_missing = [check for check in checks if check.required and not check.ready]
    optional_missing = [check for check in checks if not check.required and not check.ready]
    payload["summary"] = {
        "required_ready": not required_missing,
        "missing_required": [check.key for check in required_missing],
        "missing_optional": [check.key for check in optional_missing],
    }
    if args.format == "json":
        emit(json.dumps(payload, indent=2) + "\n", args.output)
    else:
        lines = ["DebugOracle Docs Doctor", "Checks:"]
        for check in checks:
            state = "ok" if check.ready else "missing"
            requirement = "required" if check.required else "optional"
            lines.append(f"- {check.key}: {state} ({requirement})")
            if check.remedy:
                lines.append(f"  remedy: {check.remedy}")
        if required_missing:
            lines.append("Status: blocked (required docs dependencies missing)")
        elif optional_missing:
            lines.append("Status: ready for default ingest; optional extras missing")
        else:
            lines.append("Status: fully ready")
        emit("\n".join(lines).rstrip() + "\n", args.output)

    if required_missing:
        return 1
    if optional_missing:
        return 2
    return 0


def _render_ingest(batch: DocsIngestBatch, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(batch.to_dict(), indent=2) + "\n"
    lines = ["DebugOracle Docs Ingest"]
    if batch.discovered_candidates:
        lines.append("Discovered candidates:")
        lines.extend(f"- {item}" for item in batch.discovered_candidates)
    if batch.confirmation_required:
        lines.append("Action: re-run with --yes to ingest the discovered PDFs, or pass --file/--folder.")
    if batch.results:
        lines.append("Results:")
        for result in batch.results:
            skipped_suffix = ", skipped=unchanged" if result.skipped else ""
            lines.append(
                f"- {result.source_pdf}: state={result.ingest_state}, parser={result.parser_used}, "
                f"pages={result.page_count}, chunks={result.chunk_count}{skipped_suffix}"
            )
            if result.warning_summary:
                lines.append(f"  warnings: {result.warning_summary}")
            if (
                result.ingest_state in ("partial", "warning")
                and result.parser_used == "pymupdf"
                and not _docling_installed()
            ):
                lines.append("  hint: extraction quality may improve with Docling")
                lines.append("    pipx inject debugoracle docling")
                lines.append("    # or in the active venv: pip install 'debugoracle[docling]'")
                lines.append(f"    dbgoracle docs ingest {result.source_pdf} --parser=docling")
    if batch.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in batch.warnings)
    if batch.results:
        lines.extend(_next_steps_lines(batch.results))
    return "\n".join(lines).rstrip() + "\n"


def _render_search(result: DocsSearchResult, *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(result.to_dict(), indent=2) + "\n"
    lines = [f"DebugOracle Docs Search: {result.query}"]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    if not result.hits:
        lines.append("No results.")
        return "\n".join(lines) + "\n"
    for hit in result.hits:
        lines.append(
            f"- {hit.source_pdf} pages {hit.page_start}-{hit.page_end} score={hit.score:.2f} state={hit.ingest_state}"
        )
        if hit.heading_path:
            lines.append(f"  heading: {hit.heading_path}")
        if hit.warning_summary:
            lines.append(f"  warnings: {hit.warning_summary}")
        excerpt = hit.text.replace("\n", " ")
        lines.append(f"  {excerpt[:180]}")
    return "\n".join(lines).rstrip() + "\n"


def _render_status(statuses: list[DocsStatusEntry], *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {"documents": [item.to_dict() for item in statuses]},
            indent=2,
        ) + "\n"
    lines = ["DebugOracle Docs Status"]
    if not statuses:
        lines.append("No ingested documents found.")
        return "\n".join(lines) + "\n"
    for item in statuses:
        lines.append(
            f"- {item.source_pdf}: state={item.ingest_state}, parser={item.parser_used}, "
            f"pages={item.page_count}, chunks={item.chunk_count}"
        )
        if item.warning_summary:
            lines.append(f"  warnings: {item.warning_summary}")
    return "\n".join(lines).rstrip() + "\n"


def _ingest_exit_code(batch: DocsIngestBatch) -> int:
    if batch.confirmation_required:
        return 2
    if batch.invalid_inputs:
        return 2 if batch.results else 1
    if not batch.results:
        return 1
    states = {result.ingest_state for result in batch.results}
    if "failed" in states:
        return 1
    if "partial" in states:
        return 2
    return 0


def _make_progress_cb(enabled: bool) -> ProgressCallback | None:
    if not enabled:
        return None

    def cb(current: int, total: int, label: str) -> None:
        total_safe = max(1, total)
        pct = int(100 * current / total_safe)
        print(f"\r  {label}: {current}/{total} pages ({pct}%)    ", end="", flush=True)
        if current >= total_safe:
            print()

    return cb


def _docling_installed() -> bool:
    return importlib.util.find_spec("docling") is not None


def _run_docs_ingest(
    args: argparse.Namespace,
    *,
    progress_cb: ProgressCallback | None,
) -> DocsIngestBatch:
    batch = ingest_documents(
        workspace_root=args.workspace_root,
        files=args.file,
        folders=args.folder,
        confirm_discovered=args.yes,
        parser_name=args.parser,
        semantic=args.semantic,
        force=args.force,
        progress_cb=progress_cb,
    )
    if not _interactive_enabled(args):
        return batch
    if args.file or args.folder or args.yes:
        return batch
    if not batch.confirmation_required or not batch.discovered_candidates:
        return batch
    discovered_count = len(batch.discovered_candidates)
    answer = input(f"Ingest {discovered_count} discovered PDF(s) now? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        return batch
    return ingest_documents(
        workspace_root=args.workspace_root,
        files=args.file,
        folders=args.folder,
        confirm_discovered=True,
        parser_name=args.parser,
        semantic=args.semantic,
        force=args.force,
        progress_cb=progress_cb,
    )


def _interactive_enabled(args: argparse.Namespace) -> bool:
    if getattr(args, "no_interactive", False):
        return False
    return bool(sys.stdin.isatty() and sys.stdout.isatty() and args.format == "text" and not args.output)


def _next_steps_lines(results: list[DocsIngestResult]) -> list[str]:
    lines = ["Next:"]
    first_source = results[0].source_pdf
    lines.append(f"- Search now: dbgoracle docs search \"<query>\" --file {first_source}")
    if any(result.ingest_state in {"partial", "warning"} for result in results):
        lines.append("- If quality looks degraded, retry with: --parser docling --force")
    if any(result.ingest_state == "failed" for result in results):
        lines.append("- Run diagnostics: dbgoracle docs doctor")
    return lines
