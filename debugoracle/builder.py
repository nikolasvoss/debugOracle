from __future__ import annotations

from datetime import datetime, timezone
from io import TextIOBase
from pathlib import Path

from .artifacts.models import (
    CURRENT_BUNDLE_SCHEMA_VERSION,
    InvestigationArtifact,
    MemorySource,
    RegisterSource,
)
from .pipeline.storage import build_artifact_from_sources
from .sources.debuggers.gdb.halt_snapshot import (
    GDB_HALT_SNAPSHOT_SOURCE,
    build_halt_snapshot,
)
from .sources.debuggers.gdb.peripheral_registers import (
    capture_peripheral_registers_from_svd,
    collect_peripheral_registers_from_svd,
)
from .sources.debuggers.gdb.memory import collect_memory_source_from_selectors
from .sources.debuggers.gdb.transcript import (
    GDB_TRANSCRIPT_SOURCE,
    parse_gdb_transcript,
)

DEFAULT_RTT_WINDOW = 40
FULL_RTT_WINDOW = 200

DEFAULT_SOURCE_CONTEXT: dict[str, object] = {}

__all__ = [
    "DEFAULT_RTT_WINDOW",
    "FULL_RTT_WINDOW",
    "GDB_HALT_SNAPSHOT_SOURCE",
    "GDB_TRANSCRIPT_SOURCE",
    "build_bundle_from_files",
    "build_bundle_from_stream",
    "build_bundle_from_text",
    "utc_now",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_bundle_from_files(
    gdb_mi_path: str | None = None,
    rtt_path: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
    *,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
    svd_file_path: str | None = None,
    enable_live_peripheral_capture: bool = False,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
    mem_selectors: list[str] | None = None,
) -> InvestigationArtifact:
    gdb_text = (
        _read_text_file(gdb_mi_path, errors="replace", required=True)
        if gdb_mi_path
        else ""
    )
    rtt_text = _read_text_file(rtt_path, errors="replace") if rtt_path else ""
    return build_bundle_from_text(
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_mi_path or "<missing-gdb-mi>",
        rtt_source=rtt_path,
        rtt_window=rtt_window,
        export_raw=export_raw,
        export_dir=export_dir,
        svd_file_path=svd_file_path,
        enable_live_peripheral_capture=enable_live_peripheral_capture,
        openocd_tcl_host=openocd_tcl_host,
        openocd_tcl_port=openocd_tcl_port,
        mem_selectors=mem_selectors,
    )


def build_bundle_from_stream(
    stream: TextIOBase,
    rtt_text: str = "",
    gdb_source: str = "<stdin>",
    rtt_source: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
    *,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
    svd_file_path: str | None = None,
    enable_live_peripheral_capture: bool = False,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
    mem_selectors: list[str] | None = None,
) -> InvestigationArtifact:
    gdb_text = stream.read()
    return build_bundle_from_text(
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_source,
        rtt_source=rtt_source,
        rtt_window=rtt_window,
        export_raw=export_raw,
        export_dir=export_dir,
        svd_file_path=svd_file_path,
        enable_live_peripheral_capture=enable_live_peripheral_capture,
        openocd_tcl_host=openocd_tcl_host,
        openocd_tcl_port=openocd_tcl_port,
        mem_selectors=mem_selectors,
    )


def build_bundle_from_text(
    gdb_text: str,
    rtt_text: str = "",
    gdb_source: str = "<stdin>",
    rtt_source: str | None = None,
    rtt_window: int = DEFAULT_RTT_WINDOW,
    *,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
    svd_file_path: str | None = None,
    enable_live_peripheral_capture: bool = False,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
    mem_selectors: list[str] | None = None,
) -> InvestigationArtifact:
    captured_at = utc_now()
    transcript = parse_gdb_transcript(gdb_text, now_text=lambda: "")
    halt_snapshot = build_halt_snapshot(
        latest_stop=transcript.latest_stop,
        latest_stack=transcript.latest_stack,
        latest_registers=transcript.latest_registers,
        variable_evidence=transcript.variable_evidence,
    )
    register_source = _collect_register_source(
        svd_file_path,
        gdb_text=gdb_text,
        enable_live_peripheral_capture=enable_live_peripheral_capture,
        openocd_tcl_host=openocd_tcl_host,
        openocd_tcl_port=openocd_tcl_port,
    )
    memory_source = _collect_memory_source(
        mem_selectors=mem_selectors,
        openocd_tcl_host=openocd_tcl_host,
        openocd_tcl_port=openocd_tcl_port,
    )
    artifact = build_artifact_from_sources(
        captured_at=captured_at,
        gdb_text=gdb_text,
        rtt_text=rtt_text,
        gdb_source=gdb_source,
        rtt_source=rtt_source,
        transcript=transcript,
        halt_snapshot=halt_snapshot,
        rtt_window=rtt_window,
        export_raw=export_raw,
        export_dir=export_dir,
        register_source=register_source,
        memory_source=memory_source,
    )
    artifact.schema_version = CURRENT_BUNDLE_SCHEMA_VERSION
    artifact.source_context = dict(DEFAULT_SOURCE_CONTEXT)
    return artifact


def _collect_register_source(
    svd_file_path: str | None,
    *,
    gdb_text: str,
    enable_live_peripheral_capture: bool = False,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
) -> RegisterSource | None:
    if not svd_file_path:
        return None
    if enable_live_peripheral_capture:
        return capture_peripheral_registers_from_svd(
            svd_file_path,
            mi_text=gdb_text,
            openocd_tcl_host=openocd_tcl_host,
            openocd_tcl_port=openocd_tcl_port,
        )
    return collect_peripheral_registers_from_svd(svd_file_path)


def _collect_memory_source(
    *,
    mem_selectors: list[str] | None,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
) -> MemorySource | None:
    selectors = list(mem_selectors or [])
    if not selectors:
        return None
    return collect_memory_source_from_selectors(
        selectors,
        openocd_tcl_host=openocd_tcl_host,
        openocd_tcl_port=openocd_tcl_port,
    )


def _read_text_file(
    path: str, errors: str = "strict", *, required: bool = False
) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors=errors)
    except OSError as error:
        if required:
            raise
        return f"[DEBUGORACLE_READ_ERROR {path}: {error}]"
