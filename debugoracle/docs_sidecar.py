from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

DISCOVERY_DIRECTORIES = ("debugoracle-input", "doc", "docs")
DISCOVERY_SUFFIXES = (".pdf",)
SUPPORTED_INGEST_SUFFIXES = (".pdf", ".txt", ".md", ".rst")
SIDECAR_SUFFIX = ".dbgoracle-docs"
MANAGED_DOCUMENTATION_DIRECTORY = "documentation-search"
ENVELOPE_FILENAME = "envelope.json"
INDEX_FILENAME = "index.json"
EMBEDDINGS_FILENAME = "embeddings.npy"
CHECKPOINT_FILENAME = "checkpoint.json"
CHUNKS_FILENAME = "chunks.json"
STAGED_INDEX_FILENAME = "index.staged.json"
STAGING_SUFFIX = ".staging"
_SEMANTIC_MODEL: Any | None = None

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class DocsChunk:
    chunk_id: str
    heading_path: str
    chunk_type: str
    page_start: int
    page_end: int
    text: str
    table_rows: list[list[str]] | None = None


@dataclass
class DocsEnvelope:
    source_pdf: str
    parser_used: str
    derived_paths: list[str]
    page_count: int
    chunk_count: int
    warning_summary: str
    ingest_state: str
    source_hash: str = ""
    semantic_indexed: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DocsEnvelope":
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            source_pdf=str(raw.get("source_pdf") or ""),
            parser_used=str(raw.get("parser_used") or "unknown"),
            derived_paths=[
                str(item) for item in raw.get("derived_paths", []) if item is not None
            ],
            page_count=_to_int(raw.get("page_count")),
            chunk_count=_to_int(raw.get("chunk_count")),
            warning_summary=str(raw.get("warning_summary") or ""),
            ingest_state=str(raw.get("ingest_state") or "failed"),
            source_hash=str(raw.get("source_hash") or ""),
            semantic_indexed=bool(raw.get("semantic_indexed", False)),
            warnings=[
                str(item) for item in raw.get("warnings", []) if item is not None
            ],
        )


@dataclass
class DocsIndexEntry:
    chunk_id: str
    source_pdf: str
    page_start: int
    page_end: int
    text: str
    tokens: list[str]
    token_count: int
    term_freq: dict[str, int]
    heading_path: str = ""
    chunk_type: str = "prose"
    table_rows: list[list[str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DocsIndexEntry":
        raw = raw if isinstance(raw, dict) else {}
        tokens = [str(item) for item in raw.get("tokens", []) if item is not None]
        term_freq_raw = raw.get("term_freq", {})
        term_freq = (
            {str(key): _to_int(value) for key, value in term_freq_raw.items()}
            if isinstance(term_freq_raw, dict)
            else {}
        )
        table_rows_raw = raw.get("table_rows")
        table_rows: list[list[str]] | None = None
        if isinstance(table_rows_raw, list):
            parsed_rows: list[list[str]] = []
            for row in table_rows_raw:
                if isinstance(row, list):
                    parsed_rows.append([str(cell) for cell in row])
            table_rows = parsed_rows or None

        return cls(
            chunk_id=str(raw.get("chunk_id") or ""),
            source_pdf=str(raw.get("source_pdf") or ""),
            page_start=max(1, _to_int(raw.get("page_start"), 1)),
            page_end=max(1, _to_int(raw.get("page_end"), 1)),
            text=str(raw.get("text") or ""),
            tokens=tokens,
            token_count=max(0, _to_int(raw.get("token_count"), len(tokens))),
            term_freq=term_freq,
            heading_path=str(raw.get("heading_path") or ""),
            chunk_type=str(raw.get("chunk_type") or "prose"),
            table_rows=table_rows,
        )


@dataclass
class DocsArtifact:
    envelope: DocsEnvelope
    index_entries: list[DocsIndexEntry] = field(default_factory=list)


@dataclass
class DocsParseResult:
    chunks: list[DocsChunk]
    parser_used: str
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    empty_page_count: int = 0


@dataclass
class DocsIngestCheckpoint:
    source_pdf: str
    source_hash: str
    parser_name: str
    semantic: bool
    stage: str
    parser_used: str
    page_count: int
    empty_page_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DocsIngestCheckpoint":
        return cls(
            source_pdf=str(raw.get("source_pdf") or ""),
            source_hash=str(raw.get("source_hash") or ""),
            parser_name=_canonical_parser_name(str(raw.get("parser_name") or "")),
            semantic=bool(raw.get("semantic", False)),
            stage=str(raw.get("stage") or ""),
            parser_used=str(raw.get("parser_used") or ""),
            page_count=max(0, _to_int(raw.get("page_count"))),
            empty_page_count=max(0, _to_int(raw.get("empty_page_count"))),
            warnings=[
                str(item) for item in raw.get("warnings", []) if item is not None
            ],
        )


class DocsParser(Protocol):
    def parse(
        self,
        source: Path,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> DocsParseResult: ...


@dataclass
class DocsIngestResult:
    source_pdf: str
    sidecar_dir: str
    parser_used: str
    page_count: int
    chunk_count: int
    ingest_state: str
    warning_summary: str
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocsIngestBatch:
    results: list[DocsIngestResult]
    discovered_candidates: list[str]
    warnings: list[str] = field(default_factory=list)
    confirmation_required: bool = False
    invalid_inputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocsSearchHit:
    source_pdf: str
    page_start: int
    page_end: int
    score: float
    ingest_state: str
    warning_summary: str
    text: str
    heading_path: str = ""
    table_rows: list[list[str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 3)
        return payload


@dataclass
class DocsSearchResult:
    query: str
    hits: list[DocsSearchHit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    search_mode: str = "bm25"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.search_mode,
            "results": [item.to_dict() for item in self.hits],
            "warnings": list(self.warnings),
        }


@dataclass
class DocsStatusEntry:
    source_pdf: str
    sidecar_dir: str
    envelope_path: str
    ingest_state: str
    parser_used: str
    page_count: int
    chunk_count: int
    warning_summary: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_parser(parser_name: str) -> DocsParser:
    if parser_name == "pypdf":
        return PyPDFParser()
    if parser_name == "docling":
        return DoclingParser()
    if parser_name == "plaintext":
        return PlainTextParser()
    raise ValueError(f"Unknown parser: {parser_name!r}")


def discover_candidate_documents(workspace_root: str | Path) -> list[Path]:
    candidates, _truncated = _discover_candidate_documents(workspace_root)
    return candidates


def discover_candidate_documents_bounded(
    workspace_root: str | Path,
    *,
    max_entries: int,
    max_candidates: int,
) -> tuple[list[Path], bool]:
    """Discover documents with hard traversal and result bounds."""

    if max_entries <= 0 or max_candidates <= 0:
        raise ValueError("document discovery bounds must be positive")
    return _discover_candidate_documents(
        workspace_root,
        max_entries=max_entries,
        max_candidates=max_candidates,
    )


def _discover_candidate_documents(
    workspace_root: str | Path,
    *,
    max_entries: int | None = None,
    max_candidates: int | None = None,
) -> tuple[list[Path], bool]:
    workspace = Path(workspace_root).expanduser().resolve()
    candidates: list[Path] = []
    entries_seen = 0
    try:
        root_entries = tuple(
            sorted(Path(entry.path) for entry in os.scandir(workspace))
        )
    except OSError:
        root_entries = ()
    for candidate in root_entries:
        entries_seen += 1
        if max_entries is not None and entries_seen > max_entries:
            return _dedupe_paths(sorted(candidates)), True
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if candidate.suffix.lower() in DISCOVERY_SUFFIXES:
            candidates.append(candidate.resolve())
    for directory_name in DISCOVERY_DIRECTORIES:
        candidate_dir = workspace / directory_name
        if candidate_dir.is_symlink() or not candidate_dir.is_dir():
            continue
        pending = [candidate_dir]
        while pending:
            current_dir = pending.pop()
            child_directories: list[Path] = []
            try:
                directory_entries = os.scandir(current_dir)
            except OSError:
                continue
            with directory_entries:
                for entry in directory_entries:
                    entries_seen += 1
                    if max_entries is not None and entries_seen > max_entries:
                        return _dedupe_paths(sorted(candidates)), True
                    candidate = Path(entry.path)
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if not entry.name.endswith(SIDECAR_SUFFIX):
                                child_directories.append(candidate)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    if candidate.suffix.lower() not in DISCOVERY_SUFFIXES:
                        continue
                    try:
                        resolved = candidate.resolve(strict=True)
                    except OSError:
                        continue
                    if resolved.is_file() and resolved.is_relative_to(workspace):
                        candidates.append(resolved)
                        if (
                            max_candidates is not None
                            and len(candidates) > max_candidates
                        ):
                            return (
                                _dedupe_paths(sorted(candidates))[:max_candidates],
                                True,
                            )
            pending.extend(sorted(child_directories, reverse=True))
    return _dedupe_paths(sorted(candidates)), False


def ingest_documents(
    *,
    workspace_root: str | Path,
    files: list[str] | None = None,
    folders: list[str] | None = None,
    confirm_discovered: bool = False,
    parser_name: str = "pypdf",
    semantic: bool = False,
    force: bool = False,
    progress_cb: ProgressCallback | None = None,
    managed_storage: bool = False,
) -> DocsIngestBatch:
    explicit_files = files or []
    explicit_folders = folders or []
    selected, invalid_inputs = resolve_document_inputs(
        workspace_root=workspace_root,
        files=explicit_files,
        folders=explicit_folders,
    )
    discovered: list[Path] = []
    warnings: list[str] = []
    if invalid_inputs:
        warnings.extend(invalid_inputs)
    if (explicit_files or explicit_folders) and not selected:
        return DocsIngestBatch(
            results=[],
            discovered_candidates=[],
            warnings=warnings,
            invalid_inputs=invalid_inputs,
        )
    if not selected:
        discovered = discover_candidate_documents(workspace_root)
        if not discovered:
            warnings.append("No likely PDFs were discovered under doc/ or docs/.")
            return DocsIngestBatch(
                results=[], discovered_candidates=[], warnings=warnings
            )
        if not confirm_discovered:
            warnings.append(
                "Discovered likely PDFs under doc/ or docs/; re-run with --yes or pass --file/--folder explicitly."
            )
            return DocsIngestBatch(
                results=[],
                discovered_candidates=[str(path) for path in discovered],
                warnings=warnings,
                confirmation_required=True,
                invalid_inputs=invalid_inputs,
            )
        selected = discovered

    results: list[DocsIngestResult] = []
    workspace = Path(workspace_root).expanduser().resolve()
    for source in selected:
        try:
            results.append(
                ingest_document(
                    source,
                    parser_name=parser_name,
                    semantic=semantic,
                    force=force,
                    progress_cb=progress_cb,
                    sidecar_dir=(
                        _managed_sidecar_dir_for(workspace, source)
                        if managed_storage
                        else None
                    ),
                )
            )
        except Exception as error:
            message = f"Ingest failed for '{source}': {error}"
            warnings.append(message)
            results.append(
                _build_failed_result(
                    Path(source),
                    parser_name,
                    [message],
                    sidecar_dir=(
                        _managed_sidecar_dir_for(workspace, source)
                        if managed_storage
                        else None
                    ),
                )
            )

    return DocsIngestBatch(
        results=results,
        discovered_candidates=[str(path) for path in discovered],
        warnings=warnings,
        invalid_inputs=invalid_inputs,
    )


def ingest_document(
    path: str | Path,
    *,
    parser_name: str = "pypdf",
    semantic: bool = False,
    force: bool = False,
    progress_cb: ProgressCallback | None = None,
    sidecar_dir: Path | None = None,
) -> DocsIngestResult:
    source = Path(path).expanduser().resolve()
    sidecar_dir = sidecar_dir or sidecar_dir_for(source)
    staging_dir = _staging_dir_for(sidecar_dir)
    _validate_sidecar_storage_paths(sidecar_dir)
    expected_parser = (
        "plain-text"
        if source.suffix.lower() in {".txt", ".md", ".rst"}
        else parser_name
    )

    if not force and is_ingest_fresh(
        source, sidecar_dir, parser_name=expected_parser, semantic=semantic
    ):
        artifact = load_docs_artifact(sidecar_dir)
        return DocsIngestResult(
            source_pdf=str(source),
            sidecar_dir=str(sidecar_dir),
            parser_used=artifact.envelope.parser_used,
            page_count=artifact.envelope.page_count,
            chunk_count=artifact.envelope.chunk_count,
            ingest_state=artifact.envelope.ingest_state,
            warning_summary=artifact.envelope.warning_summary,
            skipped=True,
            warnings=list(artifact.envelope.warnings),
        )
    source_hash = compute_source_hash(source) if source.exists() else ""
    if force:
        _discard_staging_dir(staging_dir)

    warnings: list[str] = []
    fatal_error: str | None = None
    parser_used = parser_name
    parse_result: DocsParseResult | None = None
    chunks: list[DocsChunk] = []
    index_entries: list[DocsIndexEntry] = []
    page_count = 0
    empty_page_count = 0
    semantic_indexed = False
    page_mapping_untrusted = False

    checkpoint = _load_checkpoint(staging_dir)
    checkpoint_compatible = _is_checkpoint_compatible(
        checkpoint=checkpoint,
        source=source,
        source_hash=source_hash,
        parser_name=expected_parser,
        semantic=semantic,
    )
    if checkpoint and not checkpoint_compatible:
        _discard_staging_dir(staging_dir)
        checkpoint = None

    if checkpoint and checkpoint.stage in {"parsed", "indexed", "embedded"}:
        parser_used = checkpoint.parser_used or parser_used
        page_count = checkpoint.page_count
        empty_page_count = checkpoint.empty_page_count
        warnings = list(checkpoint.warnings)
        chunks = _load_staged_chunks(staging_dir)
        if checkpoint.stage in {"indexed", "embedded"}:
            index_entries = _load_staged_index_entries(staging_dir)
        if checkpoint.stage == "embedded":
            semantic_indexed = semantic and (staging_dir / EMBEDDINGS_FILENAME).exists()

    try:
        if not chunks:
            if source.suffix.lower() in {".txt", ".md", ".rst"}:
                parse_result = make_parser("plaintext").parse(
                    source, progress_cb=progress_cb
                )
            elif source.suffix.lower() == ".pdf":
                if parser_name == "plaintext":
                    raise RuntimeError(
                        "Parser 'plaintext' is not supported for PDF ingestion. Use --parser=pypdf or --parser=docling."
                    )
                parse_result = make_parser(parser_name).parse(
                    source, progress_cb=progress_cb
                )
            else:
                raise RuntimeError(
                    f"Unsupported document type for ingestion: {source.suffix or '<none>'}"
                )
            parser_used = parse_result.parser_used
            warnings = list(parse_result.warnings)
            chunks = list(parse_result.chunks)
            page_count = parse_result.page_count
            empty_page_count = parse_result.empty_page_count
            if parser_used == "docling" and source.suffix.lower() == ".pdf":
                if _docling_page_mapping_untrusted(source, parse_result):
                    page_mapping_untrusted = True
                    warnings.append(
                        "docling page mapping untrusted; retrying with pypdf"
                    )
                    try:
                        fallback_result = make_parser("pypdf").parse(
                            source, progress_cb=progress_cb
                        )
                        parser_used = fallback_result.parser_used
                        warnings.extend(fallback_result.warnings)
                        warnings.append(
                            "docling page mapping untrusted; used pypdf fallback"
                        )
                        chunks = list(fallback_result.chunks)
                        page_count = fallback_result.page_count
                        empty_page_count = fallback_result.empty_page_count
                        page_mapping_untrusted = _docling_page_mapping_untrusted(
                            source, fallback_result
                        )
                        if page_mapping_untrusted:
                            warnings.append(
                                "docling page mapping untrusted; pypdf fallback page mapping still untrusted"
                            )
                    except RuntimeError as error:
                        warnings.append(
                            f"docling page mapping untrusted; pypdf fallback failed; preserved docling evidence: {error}"
                        )
            checkpoint = DocsIngestCheckpoint(
                source_pdf=str(source),
                source_hash=source_hash,
                parser_name=_canonical_parser_name(expected_parser),
                semantic=semantic,
                stage="parsed",
                parser_used=parser_used,
                page_count=page_count,
                empty_page_count=empty_page_count,
                warnings=warnings,
            )
            _save_staged_chunks(staging_dir, chunks)
            _save_checkpoint(staging_dir, checkpoint)
    except OSError as error:
        fatal_error = f"Could not read source document: {error}"
        warnings.append(fatal_error)
    except RuntimeError as error:
        fatal_error = str(error)
        warnings.append(fatal_error)

    if fatal_error is None and not index_entries:
        index_entries = build_index_entries(source, chunks)
        _save_staged_index_entries(staging_dir, index_entries)
        checkpoint = DocsIngestCheckpoint(
            source_pdf=str(source),
            source_hash=source_hash,
            parser_name=_canonical_parser_name(expected_parser),
            semantic=semantic,
            stage="indexed",
            parser_used=parser_used,
            page_count=page_count,
            empty_page_count=empty_page_count,
            warnings=warnings,
        )
        _save_checkpoint(staging_dir, checkpoint)

    if fatal_error is None and semantic and index_entries and not semantic_indexed:
        try:
            embeddings = encode_embeddings(chunks)
            save_embeddings(staging_dir, embeddings)
            semantic_indexed = True
            checkpoint = DocsIngestCheckpoint(
                source_pdf=str(source),
                source_hash=source_hash,
                parser_name=_canonical_parser_name(expected_parser),
                semantic=True,
                stage="embedded",
                parser_used=parser_used,
                page_count=page_count,
                empty_page_count=empty_page_count,
                warnings=warnings,
            )
            _save_checkpoint(staging_dir, checkpoint)
        except RuntimeError as error:
            fatal_error = str(error)
            warnings.append(fatal_error)
        except Exception as error:
            warnings.append(f"Semantic indexing failed: {error}")

    if fatal_error is not None:
        ingest_state = "failed"
    else:
        ingest_state = evaluate_ingest_state(
            page_count=page_count,
            chunk_count=len(index_entries),
            warnings=warnings,
            empty_page_count=empty_page_count,
            page_mapping_untrusted=page_mapping_untrusted,
        )

    publish_dir = _publish_dir_for(sidecar_dir)
    _discard_staging_dir(publish_dir)
    publish_dir.mkdir(parents=True, exist_ok=True)
    envelope_path = sidecar_dir / ENVELOPE_FILENAME
    index_path = sidecar_dir / INDEX_FILENAME
    derived_paths = [str(envelope_path), str(index_path)]
    if semantic_indexed:
        derived_paths.append(str(sidecar_dir / EMBEDDINGS_FILENAME))

    envelope = DocsEnvelope(
        source_pdf=str(source),
        parser_used=parser_used,
        derived_paths=derived_paths,
        page_count=page_count,
        chunk_count=len(index_entries),
        warning_summary=summarize_warnings(warnings),
        ingest_state=ingest_state,
        source_hash=compute_source_hash(source) if source.exists() else "",
        semantic_indexed=semantic_indexed,
        warnings=warnings,
    )
    save_docs_artifact(
        DocsArtifact(envelope=envelope, index_entries=index_entries), publish_dir
    )
    if semantic_indexed and (staging_dir / EMBEDDINGS_FILENAME).exists():
        shutil.copy2(
            staging_dir / EMBEDDINGS_FILENAME, publish_dir / EMBEDDINGS_FILENAME
        )
    _publish_sidecar_atomically(publish_dir=publish_dir, sidecar_dir=sidecar_dir)
    if fatal_error is None:
        _discard_staging_dir(staging_dir)

    return DocsIngestResult(
        source_pdf=str(source),
        sidecar_dir=str(sidecar_dir),
        parser_used=parser_used,
        page_count=page_count,
        chunk_count=len(index_entries),
        ingest_state=ingest_state,
        warning_summary=envelope.warning_summary,
        warnings=warnings,
    )


def resolve_document_inputs(
    *,
    workspace_root: str | Path,
    files: list[str],
    folders: list[str],
) -> tuple[list[Path], list[str]]:
    workspace = Path(workspace_root).expanduser().resolve()
    selected: list[Path] = []
    invalid_inputs: list[str] = []
    for file_path in files:
        resolved = _resolve_from_workspace(workspace, file_path)
        if resolved.is_file():
            selected.append(resolved)
        else:
            invalid_inputs.append(f"Explicit file input was not found: {resolved}")
    for folder_path in folders:
        resolved_folder = _resolve_from_workspace(workspace, folder_path)
        if not resolved_folder.is_dir():
            invalid_inputs.append(
                f"Explicit folder input was not found: {resolved_folder}"
            )
            continue
        for child in sorted(resolved_folder.rglob("*")):
            if child.is_file() and child.suffix.lower() in SUPPORTED_INGEST_SUFFIXES:
                selected.append(child.resolve())
    return (
        _dedupe_paths(
            [
                path
                for path in selected
                if path.suffix.lower() in SUPPORTED_INGEST_SUFFIXES
            ]
        ),
        invalid_inputs,
    )


def search_documents(
    *,
    workspace_root: str | Path,
    query: str,
    limit: int = 5,
    files: list[str] | None = None,
) -> DocsSearchResult:
    artifacts, warnings = load_docs_artifacts(
        workspace_root=workspace_root, files=files or []
    )
    entries = [
        (artifact.envelope, index_entry)
        for artifact in artifacts
        for index_entry in artifact.index_entries
    ]
    if not entries:
        return DocsSearchResult(query=query, warnings=warnings, search_mode="bm25")
    query_tokens = tokenize(query)
    if not query_tokens and not query.strip():
        return DocsSearchResult(query=query, warnings=warnings, search_mode="bm25")

    document_frequency = Counter()
    for _, index_entry in entries:
        document_frequency.update(set(index_entry.tokens))
    average_length = sum(max(1, entry.token_count) for _, entry in entries) / len(
        entries
    )

    bm25_scores: list[float] = []
    query_text = query.strip().lower()
    for _, index_entry in entries:
        score = _bm25_score(
            query_tokens=query_tokens,
            index_entry=index_entry,
            document_frequency=document_frequency,
            corpus_size=len(entries),
            average_length=average_length,
        )
        text_lower = index_entry.text.lower()
        if query_text and query_text in text_lower:
            score += 2.0
        bm25_scores.append(score)

    final_scores = list(bm25_scores)
    search_mode = "bm25"
    has_semantic_embeddings = any(
        (_sidecar_dir_from_envelope(envelope) / EMBEDDINGS_FILENAME).exists()
        for envelope, _ in entries
    )
    if has_semantic_embeddings:
        try:
            cosine_scores, semantic_warnings = _semantic_scores_for_entries(
                entries, query
            )
            warnings.extend(semantic_warnings)
            if cosine_scores is not None:
                normalized_bm25 = _normalize_scores(bm25_scores)
                normalized_cosine = _normalize_scores(cosine_scores)
                final_scores = [
                    0.6 * bm25 + 0.4 * cosine
                    for bm25, cosine in zip(normalized_bm25, normalized_cosine)
                ]
                search_mode = "hybrid"
        except Exception as error:
            warnings.append(f"Semantic search unavailable: {error}")

    results: list[DocsSearchHit] = []
    for score, (envelope, index_entry) in zip(final_scores, entries):
        if score <= 0:
            continue
        results.append(
            DocsSearchHit(
                source_pdf=envelope.source_pdf,
                page_start=index_entry.page_start,
                page_end=index_entry.page_end,
                score=score,
                ingest_state=envelope.ingest_state,
                warning_summary=envelope.warning_summary,
                text=index_entry.text,
                heading_path=index_entry.heading_path,
                table_rows=index_entry.table_rows,
            )
        )
    results.sort(
        key=lambda item: (-item.score, item.source_pdf, item.page_start, item.page_end)
    )
    return DocsSearchResult(
        query=query,
        hits=results[: max(1, limit)],
        warnings=warnings,
        search_mode=search_mode,
    )


def status_documents(
    *,
    workspace_root: str | Path,
    files: list[str] | None = None,
) -> list[DocsStatusEntry]:
    if files:
        targets = [
            _resolve_sidecar_dir(Path(workspace_root).expanduser().resolve(), item)
            for item in files
        ]
    else:
        targets = discover_sidecar_directories(workspace_root)
    statuses: list[DocsStatusEntry] = []
    for sidecar_dir in targets:
        envelope_path = sidecar_dir / ENVELOPE_FILENAME
        try:
            artifact = load_docs_artifact(sidecar_dir)
            envelope = artifact.envelope
            statuses.append(
                DocsStatusEntry(
                    source_pdf=envelope.source_pdf,
                    sidecar_dir=str(sidecar_dir),
                    envelope_path=str(envelope_path),
                    ingest_state=envelope.ingest_state,
                    parser_used=envelope.parser_used,
                    page_count=envelope.page_count,
                    chunk_count=envelope.chunk_count,
                    warning_summary=envelope.warning_summary,
                    warnings=envelope.warnings,
                )
            )
        except RuntimeError as error:
            source_path = str(_source_path_from_sidecar(sidecar_dir))
            statuses.append(
                DocsStatusEntry(
                    source_pdf=source_path,
                    sidecar_dir=str(sidecar_dir),
                    envelope_path=str(envelope_path),
                    ingest_state="failed",
                    parser_used="unknown",
                    page_count=0,
                    chunk_count=0,
                    warning_summary=str(error),
                    warnings=[str(error)],
                )
            )
    return sorted(statuses, key=lambda item: item.source_pdf)


def load_docs_artifacts(
    *,
    workspace_root: str | Path,
    files: list[str],
) -> tuple[list[DocsArtifact], list[str]]:
    sidecar_dirs = (
        [
            _resolve_sidecar_dir(Path(workspace_root).expanduser().resolve(), item)
            for item in files
        ]
        if files
        else discover_sidecar_directories(workspace_root)
    )
    artifacts: list[DocsArtifact] = []
    warnings: list[str] = []
    for sidecar_dir in sidecar_dirs:
        try:
            artifacts.append(load_docs_artifact(sidecar_dir))
        except RuntimeError as error:
            warnings.append(str(error))
    return artifacts, warnings


def discover_sidecar_directories(workspace_root: str | Path) -> list[Path]:
    workspace = Path(workspace_root).expanduser().resolve()
    managed_root = workspace / ".dbgoracle" / MANAGED_DOCUMENTATION_DIRECTORY
    return sorted(
        {
            path.parent.resolve()
            for path in workspace.rglob(ENVELOPE_FILENAME)
            if path.parent.name.endswith(SIDECAR_SUFFIX)
            or path.parent.is_relative_to(managed_root)
        }
    )


def load_docs_artifact(sidecar_dir: str | Path) -> DocsArtifact:
    sidecar = Path(sidecar_dir).expanduser().resolve()
    try:
        envelope_raw = json.loads(
            (sidecar / ENVELOPE_FILENAME).read_text(encoding="utf-8")
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Docs sidecar not found for '{_source_path_from_sidecar(sidecar)}'. Run `dbgoracle docs ingest` first."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Corrupt docs envelope in '{sidecar / ENVELOPE_FILENAME}': {error}"
        ) from error
    try:
        index_raw = json.loads((sidecar / INDEX_FILENAME).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Docs sidecar index is missing for '{_source_path_from_sidecar(sidecar)}'. Re-run `dbgoracle docs ingest`."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Corrupt docs index in '{sidecar / INDEX_FILENAME}': {error}"
        ) from error
    envelope = DocsEnvelope.from_dict(envelope_raw)
    if not isinstance(index_raw, list):
        raise RuntimeError(f"Corrupt docs index in '{sidecar / INDEX_FILENAME}'.")
    return DocsArtifact(
        envelope=envelope,
        index_entries=[DocsIndexEntry.from_dict(item) for item in index_raw],
    )


def save_docs_artifact(artifact: DocsArtifact, sidecar_dir: str | Path) -> None:
    sidecar = Path(sidecar_dir).expanduser().resolve()
    sidecar.mkdir(parents=True, exist_ok=True)
    (sidecar / ENVELOPE_FILENAME).write_text(
        json.dumps(artifact.envelope.to_dict(), indent=2),
        encoding="utf-8",
    )
    (sidecar / INDEX_FILENAME).write_text(
        json.dumps([entry.to_dict() for entry in artifact.index_entries], indent=2),
        encoding="utf-8",
    )


def save_embeddings(sidecar_dir: str | Path, embeddings: Any) -> None:
    sidecar = Path(sidecar_dir).expanduser().resolve()
    sidecar.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np  # pyright: ignore[reportMissingImports]
    except ImportError as error:
        raise RuntimeError(
            "Install with: pip install 'debugoracle[semantic]'"
        ) from error
    np.save(sidecar / EMBEDDINGS_FILENAME, embeddings)


def sidecar_dir_for(source_path: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    return source.with_name(f"{source.name}{SIDECAR_SUFFIX}")


def _managed_sidecar_dir_for(workspace_root: Path, source_path: Path) -> Path:
    source = source_path.resolve()
    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    return (
        workspace_root
        / ".dbgoracle"
        / MANAGED_DOCUMENTATION_DIRECTORY
        / f"{source.name}-{digest}"
    )


def _resolve_sidecar_dir(workspace_root: Path, source_path: str) -> Path:
    source = _resolve_from_workspace(workspace_root, source_path)
    managed = _managed_sidecar_dir_for(workspace_root, source)
    return (
        managed if (managed / ENVELOPE_FILENAME).is_file() else sidecar_dir_for(source)
    )


def _sidecar_dir_from_envelope(envelope: DocsEnvelope) -> Path:
    if envelope.derived_paths:
        return Path(envelope.derived_paths[0]).parent
    return sidecar_dir_for(envelope.source_pdf)


def _staging_dir_for(sidecar_dir: Path) -> Path:
    return sidecar_dir.with_name(f"{sidecar_dir.name}{STAGING_SUFFIX}")


def _publish_dir_for(sidecar_dir: Path) -> Path:
    return sidecar_dir.with_name(f"{sidecar_dir.name}.publish")


def _validate_sidecar_storage_paths(sidecar_dir: Path) -> None:
    storage_directories = (
        sidecar_dir,
        _staging_dir_for(sidecar_dir),
        _publish_dir_for(sidecar_dir),
        sidecar_dir.with_name(f"{sidecar_dir.name}.backup"),
    )
    for directory in storage_directories:
        if directory.is_symlink():
            raise RuntimeError(
                f"Refusing symbolic-link docs sidecar storage path: '{directory}'."
            )
        if directory.exists() and not directory.is_dir():
            raise RuntimeError(
                f"Docs sidecar storage path is not a directory: '{directory}'."
            )

    known_files = (
        (sidecar_dir, (ENVELOPE_FILENAME, INDEX_FILENAME, EMBEDDINGS_FILENAME)),
        (
            _staging_dir_for(sidecar_dir),
            (
                CHECKPOINT_FILENAME,
                CHUNKS_FILENAME,
                STAGED_INDEX_FILENAME,
                EMBEDDINGS_FILENAME,
            ),
        ),
    )
    for directory, filenames in known_files:
        for filename in filenames:
            path = directory / filename
            if path.is_symlink():
                raise RuntimeError(
                    f"Refusing symbolic-link docs sidecar file: '{path}'."
                )
            if path.exists() and not path.is_file():
                raise RuntimeError(
                    f"Docs sidecar path is not a regular file: '{path}'."
                )


def _discard_staging_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _load_checkpoint(staging_dir: Path) -> DocsIngestCheckpoint | None:
    checkpoint_path = staging_dir / CHECKPOINT_FILENAME
    if not checkpoint_path.exists():
        return None
    try:
        raw = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _discard_staging_dir(staging_dir)
        return None
    checkpoint = DocsIngestCheckpoint.from_dict(raw if isinstance(raw, dict) else {})
    if checkpoint.stage not in {"parsed", "indexed", "embedded"}:
        _discard_staging_dir(staging_dir)
        return None
    return checkpoint


def _save_checkpoint(staging_dir: Path, checkpoint: DocsIngestCheckpoint) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / CHECKPOINT_FILENAME).write_text(
        json.dumps(checkpoint.to_dict(), indent=2),
        encoding="utf-8",
    )


def _save_staged_chunks(staging_dir: Path, chunks: list[DocsChunk]) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / CHUNKS_FILENAME).write_text(
        json.dumps([asdict(chunk) for chunk in chunks], indent=2),
        encoding="utf-8",
    )


def _load_staged_chunks(staging_dir: Path) -> list[DocsChunk]:
    chunks_path = staging_dir / CHUNKS_FILENAME
    if not chunks_path.exists():
        _discard_staging_dir(staging_dir)
        return []
    try:
        raw = json.loads(chunks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _discard_staging_dir(staging_dir)
        return []
    if not isinstance(raw, list):
        _discard_staging_dir(staging_dir)
        return []
    chunks: list[DocsChunk] = []
    for item in raw:
        if not isinstance(item, dict):
            _discard_staging_dir(staging_dir)
            return []
        table_rows_raw = item.get("table_rows")
        table_rows: list[list[str]] | None = None
        if isinstance(table_rows_raw, list):
            rows: list[list[str]] = []
            for row in table_rows_raw:
                if isinstance(row, list):
                    rows.append([str(cell) for cell in row])
            table_rows = rows or None
        chunks.append(
            DocsChunk(
                chunk_id=str(item.get("chunk_id") or ""),
                heading_path=str(item.get("heading_path") or ""),
                chunk_type=str(item.get("chunk_type") or "prose"),
                page_start=max(1, _to_int(item.get("page_start"), 1)),
                page_end=max(1, _to_int(item.get("page_end"), 1)),
                text=str(item.get("text") or ""),
                table_rows=table_rows,
            )
        )
    return chunks


def _save_staged_index_entries(
    staging_dir: Path, entries: list[DocsIndexEntry]
) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / STAGED_INDEX_FILENAME).write_text(
        json.dumps([entry.to_dict() for entry in entries], indent=2),
        encoding="utf-8",
    )


def _load_staged_index_entries(staging_dir: Path) -> list[DocsIndexEntry]:
    index_path = staging_dir / STAGED_INDEX_FILENAME
    if not index_path.exists():
        _discard_staging_dir(staging_dir)
        return []
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _discard_staging_dir(staging_dir)
        return []
    if not isinstance(raw, list):
        _discard_staging_dir(staging_dir)
        return []
    return [
        DocsIndexEntry.from_dict(item if isinstance(item, dict) else {}) for item in raw
    ]


def _is_checkpoint_compatible(
    *,
    checkpoint: DocsIngestCheckpoint | None,
    source: Path,
    source_hash: str,
    parser_name: str,
    semantic: bool,
) -> bool:
    if checkpoint is None:
        return False
    if checkpoint.source_pdf != str(source):
        return False
    if checkpoint.source_hash != source_hash:
        return False
    if _canonical_parser_name(checkpoint.parser_name) != _canonical_parser_name(
        parser_name
    ):
        return False
    if checkpoint.semantic != semantic:
        return False
    return True


def _publish_sidecar_atomically(*, publish_dir: Path, sidecar_dir: Path) -> None:
    backup_dir = sidecar_dir.with_name(f"{sidecar_dir.name}.backup")
    _discard_staging_dir(backup_dir)
    try:
        if sidecar_dir.exists():
            os.replace(sidecar_dir, backup_dir)
        os.replace(publish_dir, sidecar_dir)
        _discard_staging_dir(backup_dir)
    except Exception:
        if publish_dir.exists():
            _discard_staging_dir(publish_dir)
        if backup_dir.exists() and not sidecar_dir.exists():
            os.replace(backup_dir, sidecar_dir)
        raise


def build_index_entries(
    source_path: str | Path, chunks: list[DocsChunk]
) -> list[DocsIndexEntry]:
    entries: list[DocsIndexEntry] = []
    source = str(Path(source_path).expanduser().resolve())
    for chunk in chunks:
        normalized = normalize_text(chunk.text)
        if not normalized:
            continue
        tokens = tokenize(normalized)
        term_freq = Counter(tokens)
        entries.append(
            DocsIndexEntry(
                chunk_id=chunk.chunk_id,
                source_pdf=source,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text=normalized,
                tokens=tokens,
                token_count=len(tokens),
                term_freq=dict(term_freq),
                heading_path=chunk.heading_path,
                chunk_type=chunk.chunk_type,
                table_rows=chunk.table_rows,
            )
        )
    return entries


def evaluate_ingest_state(
    *,
    page_count: int,
    chunk_count: int,
    warnings: list[str],
    empty_page_count: int = 0,
    page_mapping_untrusted: bool = False,
) -> str:
    if page_count <= 0:
        return "failed"
    if chunk_count <= 0:
        return "partial"
    if page_mapping_untrusted:
        return "partial"
    if empty_page_count > 0:
        return "partial"
    if warnings:
        return "partial" if chunk_count < page_count else "warning"
    if chunk_count < page_count:
        return "partial"
    return "clean"


def summarize_warnings(warnings: list[str]) -> str:
    if not warnings:
        return ""
    unique = []
    for warning in warnings:
        if warning not in unique:
            unique.append(warning)
    return "; ".join(unique[:3])


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_:/.-]+", text.lower())


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def compute_source_hash(source: Path) -> str:
    return hashlib.sha256(source.read_bytes()).hexdigest()


def is_ingest_fresh(
    source: Path,
    sidecar_dir: Path,
    *,
    parser_name: str,
    semantic: bool = False,
) -> bool:
    envelope_path = sidecar_dir / ENVELOPE_FILENAME
    if not envelope_path.exists():
        return False
    try:
        raw = json.loads(envelope_path.read_text(encoding="utf-8"))
        stored_hash = str(raw.get("source_hash") or "")
        stored_parser = _canonical_parser_name(str(raw.get("parser_used") or ""))
        ingest_state = str(raw.get("ingest_state") or "")
        parser_name = _canonical_parser_name(parser_name)
        semantic_indexed = bool(raw.get("semantic_indexed", False))
        if not stored_hash:
            return False
        if ingest_state == "failed":
            return False
        if stored_parser != parser_name:
            return False
        if semantic and not semantic_indexed:
            return False
        return stored_hash == compute_source_hash(source)
    except (OSError, json.JSONDecodeError):
        return False


class PlainTextParser:
    def parse(
        self,
        source: Path,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> DocsParseResult:
        text = source.read_text(encoding="utf-8", errors="replace")
        if progress_cb:
            progress_cb(0, 1, source.name)
            progress_cb(1, 1, source.name)
        chunk = DocsChunk(
            chunk_id="page-1",
            heading_path="",
            chunk_type="prose",
            page_start=1,
            page_end=1,
            text=text,
            table_rows=None,
        )
        return DocsParseResult(
            chunks=[chunk], parser_used="plain-text", warnings=[], page_count=1
        )


class PyPDFParser:
    def parse(
        self,
        source: Path,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> DocsParseResult:
        try:
            from pypdf import PdfReader  # pyright: ignore[reportMissingImports]
        except ImportError as error:
            raise RuntimeError(
                "pypdf is not installed in this DebugOracle environment. "
                f"Install it with: {shlex.quote(sys.executable)} -m pip install pypdf"
            ) from error

        try:
            reader = PdfReader(source)
        except Exception as error:
            raise RuntimeError(f"pypdf could not read PDF: {error}") from error
        if reader.is_encrypted:
            raise RuntimeError("pypdf cannot ingest encrypted PDFs without a password.")

        total_pages = len(reader.pages)
        if progress_cb:
            progress_cb(0, total_pages, f"{source.name} (extracting text)")
        warnings: list[str] = []
        chunks: list[DocsChunk] = []
        empty_page_count = 0
        for page_index, page in enumerate(reader.pages):
            try:
                page_text_raw = page.extract_text()
            except Exception as error:
                raise RuntimeError(
                    f"pypdf could not extract page {page_index + 1}: {error}"
                ) from error
            page_text = page_text_raw if isinstance(page_text_raw, str) else ""
            text = normalize_text(page_text)
            if not text:
                page_kind = "image-only" if _pdf_page_contains_image(page) else "empty"
                warnings.append(
                    f"Page {page_index + 1} is {page_kind}; extracted no text."
                )
                empty_page_count += 1
            else:
                page_number = page_index + 1
                rows = parse_markdown_table(text)
                chunks.append(
                    DocsChunk(
                        chunk_id=f"page-{page_number}",
                        heading_path="",
                        chunk_type=_classify_chunk_type(text, rows),
                        page_start=page_number,
                        page_end=page_number,
                        text=text,
                        table_rows=rows,
                    )
                )
            if progress_cb:
                progress_cb(page_index + 1, total_pages, source.name)

        return DocsParseResult(
            chunks=chunks,
            parser_used="pypdf",
            warnings=warnings,
            page_count=total_pages,
            empty_page_count=empty_page_count,
        )


class DoclingParser:
    def parse(
        self,
        source: Path,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> DocsParseResult:
        try:
            from docling.document_converter import (  # pyright: ignore[reportMissingImports]
                DocumentConverter,
            )
        except ModuleNotFoundError as error:
            if error.name == "docling":
                quoted_executable = shlex.quote(sys.executable)
                raise RuntimeError(
                    "Docling is not installed in this DebugOracle environment. "
                    "If using pipx, run: pipx inject debugoracle docling. "
                    f"Otherwise install in the active environment: {quoted_executable} -m pip install 'debugoracle[docling]'"
                ) from error
            raise RuntimeError(
                "Docling import failed in this DebugOracle environment. "
                f"Original error: {error}"
            ) from error
        except Exception as error:
            raise RuntimeError(
                "Docling import failed in this DebugOracle environment. "
                f"Original error: {error}"
            ) from error

        if progress_cb:
            progress_cb(0, 1, f"{source.name} (Docling -- may take 1-5 min)")
        heartbeat_stop = threading.Event()
        heartbeat_thread: threading.Thread | None = None
        start_time = time.monotonic()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(15.0):
                elapsed = int(max(0, time.monotonic() - start_time))
                if progress_cb:
                    progress_cb(
                        0, 1, f"{source.name} (Docling running, elapsed {elapsed}s)"
                    )

        if progress_cb:
            heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
            heartbeat_thread.start()

        try:
            converter = DocumentConverter()
            result = converter.convert(str(source))
        except Exception as error:
            raise RuntimeError(
                "Docling conversion failed. If running offline, pre-populate DOCLING_CACHE_HOME with models. "
                f"Original error: {error}"
            ) from error
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=0.2)

        md_raw = result.document.export_to_markdown()
        warnings: list[str] = []
        if isinstance(md_raw, str):
            md = md_raw
        else:
            md = ""
            warnings.append(
                f"Docling markdown export returned non-text output ({type(md_raw).__name__})."
            )
        chunks, split_warnings = split_markdown_by_headings(md, source, doc=None)
        warnings.extend(split_warnings)
        if not chunks:
            chunks = [
                DocsChunk(
                    chunk_id="page-1",
                    heading_path="",
                    chunk_type="prose",
                    page_start=1,
                    page_end=1,
                    text=md,
                    table_rows=parse_markdown_table(md),
                )
            ]
        if progress_cb:
            progress_cb(1, 1, source.name)

        return DocsParseResult(
            chunks=chunks,
            parser_used="docling",
            warnings=warnings,
            page_count=max(chunk.page_end for chunk in chunks),
        )


def split_markdown_by_headings(
    md: str,
    source: Path,
    doc: Any | None,
) -> tuple[list[DocsChunk], list[str]]:
    _ = source
    text = md or ""
    lines = text.splitlines()
    chunks: list[DocsChunk] = []
    warnings: list[str] = []

    heading_stack: list[str] = []
    current_heading = ""
    current_level = 1
    current_page = 1
    page_start = 1
    body_lines: list[str] = []
    heading_seen = False

    def flush_chunk(page_end: int) -> None:
        nonlocal body_lines, page_start
        body = "\n".join(body_lines).strip()
        body_lines = []
        if not body:
            page_start = current_page
            return
        chunk_id = (
            _slugify(current_heading) if current_heading else f"page-{page_start}"
        )
        table_rows = parse_markdown_table(body)
        chunks.append(
            DocsChunk(
                chunk_id=chunk_id,
                heading_path=current_heading,
                chunk_type=_classify_chunk_type(body, table_rows),
                page_start=max(1, page_start),
                page_end=max(1, page_end),
                text=body,
                table_rows=table_rows,
            )
        )
        page_start = current_page

    for line in lines:
        page_marker = _parse_page_marker(line)
        if page_marker is not None:
            flush_chunk(page_end=max(1, page_marker - 1))
            current_page = page_marker
            page_start = page_marker
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            heading_seen = True
            flush_chunk(page_end=current_page)
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            if level <= 0:
                level = 1
            current_level = level
            if len(heading_stack) < current_level:
                heading_stack.extend([""] * (current_level - len(heading_stack)))
            heading_stack = heading_stack[:current_level]
            heading_stack[current_level - 1] = heading
            current_heading = " / ".join(part for part in heading_stack if part)
            page_start = current_page
            continue

        body_lines.append(line)

    flush_chunk(page_end=current_page)

    if not heading_seen:
        if doc is not None:
            return _fallback_page_chunks(doc), warnings
        fallback = normalize_text(text)
        if not fallback:
            return [], warnings
        rows = parse_markdown_table(fallback)
        return [
            DocsChunk(
                chunk_id="page-1",
                heading_path="",
                chunk_type=_classify_chunk_type(fallback, rows),
                page_start=1,
                page_end=1,
                text=fallback,
                table_rows=rows,
            )
        ], warnings

    if not chunks and doc is not None:
        return _fallback_page_chunks(doc), warnings
    return chunks, warnings


def parse_markdown_table(text: str) -> list[list[str]] | None:
    rows: list[list[str]] = []
    block_lines: list[str] = []

    def flush_block() -> None:
        nonlocal block_lines
        if len(block_lines) < 2:
            block_lines = []
            return
        for line in block_lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not cells:
                continue
            if all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
                continue
            rows.append(cells)
        block_lines = []

    for line in text.splitlines():
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|"):
            block_lines.append(stripped)
            continue
        flush_block()
    flush_block()
    return rows or None


def encode_embeddings(chunks: list[DocsChunk]) -> Any:
    try:
        import numpy as np  # pyright: ignore[reportMissingImports]
    except ImportError as error:
        raise RuntimeError(
            "Install with: pip install 'debugoracle[semantic]'"
        ) from error
    model = _get_semantic_model()
    texts = [chunk.text for chunk in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    if not isinstance(embeddings, np.ndarray):
        embeddings = np.asarray(embeddings)
    return embeddings


def _semantic_scores_for_entries(
    entries: list[tuple[DocsEnvelope, DocsIndexEntry]],
    query: str,
) -> tuple[list[float] | None, list[str]]:
    try:
        import numpy as np  # pyright: ignore[reportMissingImports]
    except ImportError as error:
        return None, [f"Semantic search unavailable: {error}"]

    model = _get_semantic_model()
    query_embedding = model.encode(
        [query], convert_to_numpy=True, show_progress_bar=False
    )
    query_vector = query_embedding[0]

    grouped: dict[str, list[tuple[int, DocsEnvelope, DocsIndexEntry]]] = {}
    for idx, (envelope, entry) in enumerate(entries):
        grouped.setdefault(envelope.source_pdf, []).append((idx, envelope, entry))

    scores = [0.0] * len(entries)
    warnings: list[str] = []

    for source_pdf, group in grouped.items():
        sidecar_dir = _sidecar_dir_from_envelope(group[0][1])
        embeddings_path = sidecar_dir / EMBEDDINGS_FILENAME
        if not embeddings_path.exists():
            continue
        try:
            embeddings = np.load(embeddings_path)
            if embeddings.ndim == 1:
                embeddings = embeddings.reshape(1, -1)
            if embeddings.shape[0] != len(group):
                warnings.append(
                    f"Semantic embeddings row count mismatch for '{source_pdf}'; falling back to BM25 for this file."
                )
                continue
            denom = np.linalg.norm(embeddings, axis=1) * max(
                np.linalg.norm(query_vector), 1e-12
            )
            cosine = np.dot(embeddings, query_vector) / np.maximum(denom, 1e-12)
            for (global_index, _, _), cosine_value in zip(group, cosine):
                scores[global_index] = float(cosine_value)
        except Exception as error:
            warnings.append(
                f"Could not read semantic embeddings for '{source_pdf}': {error}. Falling back to BM25 for this file."
            )

    return scores, warnings


def _normalize_scores(scores: list[float]) -> list[float]:
    min_score = min(scores, default=0.0)
    max_score = max(scores, default=1.0)
    if max_score == min_score:
        return [1.0 if score > 0 else 0.0 for score in scores]
    return [(score - min_score) / (max_score - min_score) for score in scores]


def _build_semantic_model() -> Any:
    from sentence_transformers import (  # pyright: ignore[reportMissingImports]
        SentenceTransformer,
    )

    return SentenceTransformer("all-MiniLM-L6-v2")


def _get_semantic_model() -> Any:
    global _SEMANTIC_MODEL
    if _SEMANTIC_MODEL is None:
        _SEMANTIC_MODEL = _build_semantic_model()
    return _SEMANTIC_MODEL


def _bm25_score(
    *,
    query_tokens: list[str],
    index_entry: DocsIndexEntry,
    document_frequency: Counter[str],
    corpus_size: int,
    average_length: float,
) -> float:
    score = 0.0
    k1 = 1.5
    b = 0.75
    doc_length = max(1, index_entry.token_count)
    for token in set(query_tokens):
        term_frequency = index_entry.term_freq.get(token, 0)
        if term_frequency <= 0:
            continue
        doc_freq = document_frequency.get(token, 0)
        inverse_document_frequency = math.log(
            1.0 + (corpus_size - doc_freq + 0.5) / (doc_freq + 0.5)
        )
        denominator = term_frequency + k1 * (
            1.0 - b + b * (doc_length / max(1.0, average_length))
        )
        score += inverse_document_frequency * (
            term_frequency * (k1 + 1.0) / max(1.0, denominator)
        )
    return score


def _resolve_from_workspace(workspace_root: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = workspace_root / path
    return path.resolve()


def _source_path_from_sidecar(sidecar_dir: Path) -> Path:
    name = sidecar_dir.name
    if name.endswith(SIDECAR_SUFFIX):
        return sidecar_dir.with_name(name[: -len(SIDECAR_SUFFIX)])
    return sidecar_dir


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _canonical_parser_name(name: str) -> str:
    return "plain-text" if name == "plaintext" else name


def _slugify(heading_path: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", heading_path.lower()).strip("-")
    return f"sec-{cleaned}" if cleaned else "page-1"


def _parse_page_marker(line: str) -> int | None:
    # Optional adapters may emit markers like: <!-- Page 3 -->
    match = re.search(r"<!--\s*Page\s+(\d+)\s*-->", line, flags=re.IGNORECASE)
    if match:
        return max(1, int(match.group(1)))
    return None


def _classify_chunk_type(text: str, table_rows: list[list[str]] | None) -> str:
    if not table_rows:
        return "prose"
    non_table_lines = [line for line in text.splitlines() if "|" not in line]
    return "table" if not any(line.strip() for line in non_table_lines) else "mixed"


def _fallback_page_chunks(doc: Any) -> list[DocsChunk]:
    chunks: list[DocsChunk] = []
    for page_index in range(len(doc)):
        page_num = page_index + 1
        try:
            page_md = doc[page_index].get_text("markdown") or ""
        except Exception:
            page_md = ""
        normalized = normalize_text(page_md)
        if not normalized:
            continue
        rows = parse_markdown_table(normalized)
        chunks.append(
            DocsChunk(
                chunk_id=f"page-{page_num}",
                heading_path="",
                chunk_type=_classify_chunk_type(normalized, rows),
                page_start=page_num,
                page_end=page_num,
                text=normalized,
                table_rows=rows,
            )
        )
    return chunks


def _pdf_page_count(source: Path) -> int | None:
    try:
        from pypdf import PdfReader  # pyright: ignore[reportMissingImports]
    except Exception:
        return None
    try:
        return int(len(PdfReader(source).pages))
    except Exception:
        return None


def _pdf_page_contains_image(page: Any) -> bool:
    try:
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        return any(
            item.get_object().get("/Subtype") == "/Image" for item in xobjects.values()
        )
    except (AttributeError, KeyError, TypeError):
        return False


def _docling_page_mapping_untrusted(
    source: Path, parse_result: DocsParseResult
) -> bool:
    total_pages = _pdf_page_count(source)
    if total_pages is None or total_pages <= 1:
        return False
    if not parse_result.chunks:
        return False
    return all(
        chunk.page_start == 1 and chunk.page_end == 1 for chunk in parse_result.chunks
    )


def _build_failed_result(
    source: Path,
    parser_name: str,
    warnings: list[str],
    sidecar_dir: Path | None = None,
) -> DocsIngestResult:
    sidecar_dir = sidecar_dir or sidecar_dir_for(source)
    envelope_path = sidecar_dir / ENVELOPE_FILENAME
    index_path = sidecar_dir / INDEX_FILENAME
    storage_safe = True
    try:
        _validate_sidecar_storage_paths(sidecar_dir)
    except RuntimeError as error:
        storage_safe = False
        message = str(error)
        if message not in warnings:
            warnings.append(message)
    envelope = DocsEnvelope(
        source_pdf=str(source.resolve()),
        parser_used=parser_name,
        derived_paths=[str(envelope_path), str(index_path)],
        page_count=0,
        chunk_count=0,
        warning_summary=summarize_warnings(warnings),
        ingest_state="failed",
        source_hash=compute_source_hash(source) if source.exists() else "",
        semantic_indexed=False,
        warnings=warnings,
    )
    if storage_safe:
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        save_docs_artifact(
            DocsArtifact(envelope=envelope, index_entries=[]), sidecar_dir
        )
    return DocsIngestResult(
        source_pdf=str(source.resolve()),
        sidecar_dir=str(sidecar_dir),
        parser_used=parser_name,
        page_count=0,
        chunk_count=0,
        ingest_state="failed",
        warning_summary=envelope.warning_summary,
        warnings=warnings,
    )
