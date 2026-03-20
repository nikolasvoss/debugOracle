from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..artifacts.models import ArtifactSources, EvidenceBundle, GdbSource, RegisterSource, RttSource, VariableEvidence


def build_artifact_from_sources(
    *,
    captured_at: str,
    gdb_text: str,
    rtt_text: str,
    gdb_source: str,
    rtt_source: str | None,
    transcript: Any,
    halt_snapshot: Any,
    rtt_window: int,
    export_raw: bool = False,
    export_dir: str | Path | None = None,
    register_source: RegisterSource | None = None,
) -> EvidenceBundle:
    recent_rtt = _select_recent_rtt(rtt_text, rtt_window)

    if not recent_rtt:
        transcript.parse_warnings.append("No RTT lines were available for this snapshot.")
        transcript.parse_event_counts["missing-rtt"] = transcript.parse_event_counts.get("missing-rtt", 0) + 1
        transcript.parse_event_severity_counts["warn"] = transcript.parse_event_severity_counts.get("warn", 0) + 1

    if transcript.non_mi_line_count:
        transcript.parse_warnings.append(
            "Transcript noise retained as context: "
            f"{transcript.noise_line_counts.get('prompt-marker', 0)} prompt markers, "
            f"{transcript.noise_line_counts.get('console-output', 0)} console-output lines, "
            f"{transcript.noise_line_counts.get('non_mi_line', 0)} other non-MI lines. "
            "The snapshot embeds the full transcript for later inspection."
        )

    critical_events: list[str] = []
    if not gdb_text:
        critical_events.append("No GDB/MI input was provided before building this snapshot.")
        transcript.parse_event_counts["critical-missing-input"] = transcript.parse_event_counts.get("critical-missing-input", 0) + 1
        transcript.parse_event_severity_counts["warn"] = transcript.parse_event_severity_counts.get("warn", 0) + 1
    if transcript.latest_stop is None:
        critical_events.append("Could not recover a stop context from the transcript.")

    quality_score = _compute_evidence_quality_score(
        latest_stop=transcript.latest_stop,
        latest_stack=halt_snapshot.frames,
        latest_registers=halt_snapshot.registers,
        variable_evidence=halt_snapshot.variable_evidence,
        parse_error_count=transcript.mi_parse_error_count,
        warning_count=len(transcript.parse_warnings),
    )

    raw_export: dict[str, Any] = {}
    if export_dir is not None:
        should_export = export_raw or bool(
            transcript.non_mi_line_count or transcript.mi_parse_error_count or not gdb_text
        )
        if should_export:
            raw_export["raw_exported"] = True
            raw_export.update(
                _export_raw_inputs(
                    gdb_text=gdb_text,
                    rtt_text=rtt_text,
                    export_dir=Path(export_dir),
                )
            )

    gdb_events = list(transcript.session_events)
    rtt_lines = [line.rstrip() for line in rtt_text.splitlines()]
    has_gdb_source = bool(gdb_text) or gdb_source not in {"<missing-gdb-mi>", "<stdin>"}
    has_rtt_source = bool(rtt_text) or rtt_source is not None
    sources = ArtifactSources(
        gdb=GdbSource(
            raw_text=gdb_text if has_gdb_source else None,
            events=gdb_events,
            event_count=len(gdb_events),
            embedded=has_gdb_source,
        ),
        rtt=RttSource(
            raw_text=rtt_text if has_rtt_source else None,
            lines=rtt_lines,
            line_count=len(rtt_lines),
            embedded=has_rtt_source,
        ),
        registers=register_source or RegisterSource(embedded=False),
    )

    register_provenance: dict[str, Any] = {}
    if sources.registers.embedded:
        register_provenance = {
            "register_svd_source": sources.registers.svd_source,
            "register_device_name": sources.registers.device_name,
            "register_peripheral_count": sources.registers.peripheral_count,
            "register_count": sources.registers.register_count,
            "register_success_count": sources.registers.success_count,
            "register_failure_count": sources.registers.failure_count,
            "register_skipped_count": sources.registers.skipped_count,
        }

    return EvidenceBundle(
        snapshot_id=_make_snapshot_id(gdb_text, rtt_text, captured_at),
        captured_at=captured_at,
        stop_reason=halt_snapshot.stop_reason,
        pc=halt_snapshot.pc,
        lr=halt_snapshot.lr,
        sp=halt_snapshot.sp,
        frames=halt_snapshot.frames,
        registers=halt_snapshot.registers,
        variable_evidence=halt_snapshot.variable_evidence,
        sources=sources,
        recent_rtt=recent_rtt,
        parse_warnings=transcript.parse_warnings,
        source_context={},
        provenance={
            "gdb_mi_source": gdb_source,
            "rtt_source": rtt_source,
            "gdb_event_count": len(gdb_events),
            "rtt_line_count": len(recent_rtt),
            "rtt_total_line_count": len(rtt_lines),
            "rtt_window": rtt_window,
            "parse_warning_count": len(transcript.parse_warnings),
            "mi_record_count": transcript.mi_record_count,
            "non_mi_line_count": transcript.non_mi_line_count,
            "mi_parse_error_count": transcript.mi_parse_error_count,
            "evidence_quality_score": quality_score,
            "parse_event_counts": dict(transcript.parse_event_counts),
            "parse_event_severity_counts": dict(transcript.parse_event_severity_counts),
            "critical_warnings": critical_events,
            "critical_warning_count": len(critical_events),
            "non_mi_pattern_counts": [
                {"pattern": _normalize_non_mi_pattern_key(pattern), "count": int(count)}
                for pattern, count in transcript.noise_pattern_counts.most_common(8)
            ],
            "raw_line_warning_count": transcript.non_mi_line_count,
            **register_provenance,
            **raw_export,
        },
        session_events=gdb_events,
    )


def _select_recent_rtt(rtt_text: str, rtt_window: int) -> list[str]:
    lines = [line.rstrip() for line in rtt_text.splitlines() if line.strip()]
    if rtt_window <= 0:
        return []
    return lines[-rtt_window:] if len(lines) > rtt_window else lines


def _normalize_non_mi_pattern_key(value: str) -> str:
    normalized = (
        value.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return " ".join(normalized.split()) or "<empty>"


def _compute_evidence_quality_score(
    latest_stop: dict[str, Any] | None,
    latest_stack: list[object],
    latest_registers: dict[str, str],
    variable_evidence: VariableEvidence,
    parse_error_count: int,
    warning_count: int,
) -> int:
    score = 100
    if latest_stop is None:
        score -= 30
    if not latest_stack:
        score -= 20
    if not latest_registers:
        score -= 20
    if variable_evidence.count() == 0:
        score -= 15
    score -= min(25, parse_error_count * 8)
    score -= min(5, warning_count // 4)
    return max(0, score)


def _export_raw_inputs(
    *,
    gdb_text: str,
    rtt_text: str,
    export_dir: Path,
) -> dict[str, Any]:
    export_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"raw_export_root": str(export_dir)}
    if gdb_text:
        gdb_path = export_dir / "raw-gdb-mi.log"
        gdb_path.write_text(gdb_text, encoding="utf-8")
        payload["gdb_mi_raw_path"] = str(gdb_path)
        payload["gdb_mi_raw_bytes"] = gdb_path.stat().st_size
    if rtt_text:
        rtt_path = export_dir / "raw-rtt.log"
        rtt_path.write_text(rtt_text, encoding="utf-8")
        payload["rtt_raw_path"] = str(rtt_path)
        payload["rtt_raw_bytes"] = rtt_path.stat().st_size
    return payload


def _make_snapshot_id(gdb_text: str, rtt_text: str, captured_at: str) -> str:
    digest = hashlib.sha1(f"{captured_at}\n{gdb_text}\n{rtt_text}".encode("utf-8")).hexdigest()
    return f"snap-{digest[:12]}"
