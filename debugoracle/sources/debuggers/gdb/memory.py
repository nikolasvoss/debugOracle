from __future__ import annotations

from dataclasses import dataclass

from ...base import SourceDescriptor, validate_source_descriptor

GDB_MEMORY_SOURCE = validate_source_descriptor(
    SourceDescriptor(
        source_id="gdb_memory",
        family="snapshot",
        trigger="on_halt",
        requires_halt=True,
        persistence_default="artifact",
        backend_dependency="gdb",
        supports_parsing=False,
        supports_reduction=True,
    )
)


@dataclass(frozen=True)
class GdbMemorySnapshot:
    address: str
    size: int
    data_hex: str


def collect_gdb_memory_read(*, address: str, size: int, data_hex: str) -> GdbMemorySnapshot:
    return GdbMemorySnapshot(
        address=address,
        size=size,
        data_hex=data_hex,
    )
