from __future__ import annotations

from ...base import SourceDescriptor, validate_source_descriptor

GDB_REGISTERS_SOURCE = validate_source_descriptor(
    SourceDescriptor(
        source_id="gdb_registers",
        family="snapshot",
        trigger="on_halt",
        requires_halt=True,
        persistence_default="artifact",
        backend_dependency="gdb",
        supports_parsing=False,
        supports_reduction=True,
    )
)


def collect_gdb_registers(registers: dict[str, str]) -> dict[str, str]:
    return dict(registers)
