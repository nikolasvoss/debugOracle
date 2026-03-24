from __future__ import annotations

import argparse
import json

from ...docs_sidecar import ingest_documents, search_documents, status_documents
from .status_capture import emit


def cmd_docs_ingest(args: argparse.Namespace) -> int:
    batch = ingest_documents(
        workspace_root=args.workspace_root,
        files=args.file,
        folders=args.folder,
        confirm_discovered=args.yes,
    )
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


def _render_ingest(batch: object, *, fmt: str) -> str:
    if fmt == "json":
        payload = batch.to_dict()  # type: ignore[call-arg]
        return json.dumps(payload, indent=2) + "\n"
    lines = ["DebugOracle Docs Ingest"]
    results = getattr(batch, "results", [])
    warnings = getattr(batch, "warnings", [])
    discovered = getattr(batch, "discovered_candidates", [])
    confirmation_required = getattr(batch, "confirmation_required", False)
    if discovered:
        lines.append("Discovered candidates:")
        lines.extend(f"- {item}" for item in discovered)
    if confirmation_required:
        lines.append("Action: re-run with --yes to ingest the discovered PDFs, or pass --file/--folder.")
    if results:
        lines.append("Results:")
        for result in results:
            lines.append(
                f"- {result.source_pdf}: state={result.ingest_state}, parser={result.parser_used}, "
                f"pages={result.page_count}, chunks={result.chunk_count}"
            )
            if result.warning_summary:
                lines.append(f"  warnings: {result.warning_summary}")
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines).rstrip() + "\n"


def _render_search(result: object, *, fmt: str) -> str:
    if fmt == "json":
        payload = result.to_dict()  # type: ignore[call-arg]
        return json.dumps(payload, indent=2) + "\n"
    query = getattr(result, "query", "")
    hits = getattr(result, "hits", [])
    warnings = getattr(result, "warnings", [])
    lines = [f"DebugOracle Docs Search: {query}"]
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    if not hits:
        lines.append("No results.")
        return "\n".join(lines) + "\n"
    for hit in hits:
        lines.append(
            f"- {hit.source_pdf} pages {hit.page_start}-{hit.page_end} score={hit.score:.2f} state={hit.ingest_state}"
        )
        if hit.warning_summary:
            lines.append(f"  warnings: {hit.warning_summary}")
        excerpt = hit.text.replace("\n", " ")
        lines.append(f"  {excerpt[:180]}")
    return "\n".join(lines).rstrip() + "\n"


def _render_status(statuses: list[object], *, fmt: str) -> str:
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


def _ingest_exit_code(batch: object) -> int:
    if getattr(batch, "confirmation_required", False):
        return 2
    if getattr(batch, "invalid_inputs", []):
        return 2 if getattr(batch, "results", []) else 1
    results = getattr(batch, "results", [])
    if not results:
        return 1
    states = {result.ingest_state for result in results}
    if "failed" in states:
        return 1
    if "partial" in states:
        return 2
    return 0
