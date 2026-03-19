from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....artifacts.models import StackFrame, VariableEvidence
from ...base import SourceDescriptor, validate_source_descriptor
from .transcript import extract_pc, normalize_frame

GDB_HALT_SNAPSHOT_SOURCE = validate_source_descriptor(
    SourceDescriptor(
        source_id="gdb_halt_snapshot",
        family="snapshot",
        trigger="on_halt",
        requires_halt=True,
        persistence_default="artifact",
        backend_dependency="gdb-mi",
        supports_parsing=True,
        supports_reduction=True,
    )
)


@dataclass
class GdbHaltSnapshot:
    stop_reason: str | None
    pc: str | None
    lr: str | None
    sp: str | None
    frames: list[StackFrame]
    registers: dict[str, str]
    variable_evidence: VariableEvidence


def build_halt_snapshot(
    *,
    latest_stop: dict[str, Any] | None,
    latest_stack: list[StackFrame],
    latest_registers: dict[str, str],
    variable_evidence: VariableEvidence,
) -> GdbHaltSnapshot:
    frames = latest_stack
    if not frames and latest_stop:
        frame = latest_stop.get("frame")
        if isinstance(frame, dict):
            frames = [normalize_frame(frame, default_level=0)]
    return GdbHaltSnapshot(
        stop_reason=_as_text(latest_stop.get("reason")) if latest_stop else None,
        pc=extract_pc(latest_stop, latest_registers, frames),
        lr=latest_registers.get("14"),
        sp=latest_registers.get("13"),
        frames=frames,
        registers=latest_registers,
        variable_evidence=variable_evidence,
    )


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
