from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DISCOVERY_DIRECTORIES = ("doc", "docs")
DISCOVERY_SUFFIXES = (".pdf",)
SUPPORTED_INGEST_SUFFIXES = (".pdf", ".txt", ".md", ".rst")
SIDECAR_SUFFIX = ".dbgoracle-docs"
ENVELOPE_FILENAME = "envelope.json"
INDEX_FILENAME = "index.json"


@dataclass
class DocsEnvelope:
    source_pdf: str
    parser_used: str
    derived_paths: list[str]
    page_count: int
    chunk_count: int
    warning_summary: str
    ingest_state: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DocsEnvelope":
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            source_pdf=str(raw.get("source_pdf") or ""),
            parser_used=str(raw.get("parser_used") or "unknown"),
            derived_paths=[str(item) for item in raw.get("derived_paths", []) if item is not None],
            page_count=_to_int(raw.get("page_count")),
            chunk_count=_to_int(raw.get("chunk_count")),
            warning_summary=str(raw.get("warning_summary") or ""),
            ingest_state=str(raw.get("ingest_state") or "failed"),
            warnings=[str(item) for item in raw.get("warnings", []) if item is not None],
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DocsIndexEntry":
        raw = raw if isinstance(raw, dict) else {}
        tokens = [str(item) for item in raw.get("tokens", []) if item is not None]
        term_freq_raw = raw.get("term_freq", {})
        term_freq = {
            str(key): _to_int(value)
            for key, value in term_freq_raw.items()
        } if isinstance(term_freq_raw, dict) else {}
        return cls(
            chunk_id=str(raw.get("chunk_id") or ""),
            source_pdf=str(raw.get("source_pdf") or ""),
            page_start=max(1, _to_int(raw.get("page_start"), 1)),
            page_end=max(1, _to_int(raw.get("page_end"), 1)),
            text=str(raw.get("text") or ""),
            tokens=tokens,
            token_count=max(0, _to_int(raw.get("token_count"), len(tokens))),
            term_freq=term_freq,
        )


@dataclass
class DocsArtifact:
    envelope: DocsEnvelope
    index_entries: list[DocsIndexEntry] = field(default_factory=list)


@dataclass
class DocsIngestResult:
    source_pdf: str
    sidecar_dir: str
    parser_used: str
    page_count: int
    chunk_count: int
    ingest_state: str
    warning_summary: str
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

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 3)
        return payload


@dataclass
class DocsSearchResult:
    query: str
    hits: list[DocsSearchHit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
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


def discover_candidate_documents(workspace_root: str | Path) -> list[Path]:
    workspace = Path(workspace_root).expanduser().resolve()
    candidates: list[Path] = []
    for directory_name in DISCOVERY_DIRECTORIES:
        candidate_dir = workspace / directory_name
        if not candidate_dir.is_dir():
            continue
        for suffix in DISCOVERY_SUFFIXES:
            candidates.extend(sorted(candidate_dir.rglob(f"*{suffix}")))
    return _dedupe_paths(candidates)


def ingest_documents(
    *,
    workspace_root: str | Path,
    files: list[str] | None = None,
    folders: list[str] | None = None,
    confirm_discovered: bool = False,
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
            return DocsIngestBatch(results=[], discovered_candidates=[], warnings=warnings)
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

    results = [ingest_document(path) for path in selected]
    return DocsIngestBatch(
        results=results,
        discovered_candidates=[str(path) for path in discovered],
        warnings=warnings,
        invalid_inputs=invalid_inputs,
    )


def ingest_document(path: str | Path) -> DocsIngestResult:
    source = Path(path).expanduser().resolve()
    pages: list[str] = []
    warnings: list[str] = []
    parser_used = "unknown"
    fatal_error: str | None = None
    try:
        pages, parser_used, warnings = _extract_document_pages(source)
    except OSError as error:
        fatal_error = f"Could not read source document: {error}"
        warnings.append(fatal_error)
    except RuntimeError as error:
        fatal_error = str(error)
        warnings.append(fatal_error)

    index_entries = build_index_entries(source, pages)
    if fatal_error is not None:
        ingest_state = "failed"
    else:
        ingest_state = evaluate_ingest_state(
            page_count=len(pages),
            chunk_count=len(index_entries),
            warnings=warnings,
        )
    sidecar_dir = sidecar_dir_for(source)
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    envelope_path = sidecar_dir / ENVELOPE_FILENAME
    index_path = sidecar_dir / INDEX_FILENAME
    envelope = DocsEnvelope(
        source_pdf=str(source),
        parser_used=parser_used,
        derived_paths=[str(envelope_path), str(index_path)],
        page_count=len(pages),
        chunk_count=len(index_entries),
        warning_summary=summarize_warnings(warnings),
        ingest_state=ingest_state,
        warnings=warnings,
    )
    save_docs_artifact(DocsArtifact(envelope=envelope, index_entries=index_entries), sidecar_dir)
    return DocsIngestResult(
        source_pdf=str(source),
        sidecar_dir=str(sidecar_dir),
        parser_used=parser_used,
        page_count=len(pages),
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
            invalid_inputs.append(f"Explicit folder input was not found: {resolved_folder}")
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
    artifacts, warnings = load_docs_artifacts(workspace_root=workspace_root, files=files or [])
    entries = [
        (artifact.envelope, index_entry)
        for artifact in artifacts
        for index_entry in artifact.index_entries
    ]
    if not entries:
        return DocsSearchResult(query=query, warnings=warnings)
    query_tokens = tokenize(query)
    if not query_tokens and not query.strip():
        return DocsSearchResult(query=query, warnings=warnings)
    document_frequency = Counter()
    for _, index_entry in entries:
        document_frequency.update(set(index_entry.tokens))
    average_length = sum(max(1, entry.token_count) for _, entry in entries) / len(entries)
    results: list[DocsSearchHit] = []
    query_text = query.strip().lower()
    for envelope, index_entry in entries:
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
            )
        )
    results.sort(key=lambda item: (-item.score, item.source_pdf, item.page_start, item.page_end))
    return DocsSearchResult(
        query=query,
        hits=results[: max(1, limit)],
        warnings=warnings,
    )


def status_documents(
    *,
    workspace_root: str | Path,
    files: list[str] | None = None,
) -> list[DocsStatusEntry]:
    if files:
        targets = [
            sidecar_dir_for(_resolve_from_workspace(Path(workspace_root).expanduser().resolve(), item))
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
            sidecar_dir_for(_resolve_from_workspace(Path(workspace_root).expanduser().resolve(), item))
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
    return sorted(
        {
            path.parent.resolve()
            for path in workspace.rglob(ENVELOPE_FILENAME)
            if path.parent.name.endswith(SIDECAR_SUFFIX)
        }
    )


def load_docs_artifact(sidecar_dir: str | Path) -> DocsArtifact:
    sidecar = Path(sidecar_dir).expanduser().resolve()
    try:
        envelope_raw = json.loads((sidecar / ENVELOPE_FILENAME).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Docs sidecar not found for '{_source_path_from_sidecar(sidecar)}'. Run `dbgoracle docs ingest` first."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Corrupt docs envelope in '{sidecar / ENVELOPE_FILENAME}': {error}") from error
    try:
        index_raw = json.loads((sidecar / INDEX_FILENAME).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Docs sidecar index is missing for '{_source_path_from_sidecar(sidecar)}'. Re-run `dbgoracle docs ingest`."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Corrupt docs index in '{sidecar / INDEX_FILENAME}': {error}") from error
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


def sidecar_dir_for(source_path: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    return source.with_name(f"{source.name}{SIDECAR_SUFFIX}")


def build_index_entries(source_path: str | Path, pages: list[str]) -> list[DocsIndexEntry]:
    entries: list[DocsIndexEntry] = []
    source = str(Path(source_path).expanduser().resolve())
    for page_number, page_text in enumerate(pages, start=1):
        normalized = normalize_text(page_text)
        if not normalized:
            continue
        tokens = tokenize(normalized)
        term_freq = Counter(tokens)
        entries.append(
            DocsIndexEntry(
                chunk_id=f"page-{page_number}",
                source_pdf=source,
                page_start=page_number,
                page_end=page_number,
                text=normalized,
                tokens=tokens,
                token_count=len(tokens),
                term_freq=dict(term_freq),
            )
        )
    return entries


def evaluate_ingest_state(*, page_count: int, chunk_count: int, warnings: list[str]) -> str:
    if page_count <= 0:
        return "failed"
    if chunk_count <= 0:
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


def _extract_document_pages(source: Path) -> tuple[list[str], str, list[str]]:
    suffix = source.suffix.lower()
    if suffix in {".txt", ".md", ".rst"}:
        text = source.read_text(encoding="utf-8", errors="replace")
        return [text], "plain-text", []
    if suffix == ".pdf":
        return _extract_pdf_pages(source)
    raise RuntimeError(f"Unsupported document type for ingestion: {source.suffix or '<none>'}")


def _extract_pdf_pages(source: Path) -> tuple[list[str], str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "PDF parsing requires the optional 'pypdf' package for dbgoracle docs ingest."
        ) from error

    reader = PdfReader(str(source))
    pages: list[str] = []
    warnings: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if not text:
            warnings.append(f"Page {page_number} extracted no text.")
        pages.append(text)
    return pages, "pypdf", warnings


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
        denominator = term_frequency + k1 * (1.0 - b + b * (doc_length / max(1.0, average_length)))
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
