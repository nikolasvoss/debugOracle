from __future__ import annotations

from dataclasses import dataclass
import os

from ....artifacts.models import MemoryReadEntry, MemorySource
from ....policy.limits import validate_bounded_memory_read
from .peripheral_registers import (
    OPENOCD_DEFAULT_HOST,
    OPENOCD_HOST_ENV,
    OPENOCD_PORT_ENV,
    OpenOcdMemoryReader,
    _resolve_openocd_port,
)
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


MAX_FETCH_MEMORY_READ_BYTES = 256
MEMORY_READ_CHUNK_BYTES = 32


def collect_gdb_memory_read(
    *, address: str, size: int, data_hex: str
) -> GdbMemorySnapshot:
    return GdbMemorySnapshot(
        address=address,
        size=size,
        data_hex=data_hex,
    )


def parse_memory_selector(
    selector: str,
    *,
    max_bytes: int = MAX_FETCH_MEMORY_READ_BYTES,
) -> tuple[str, int, int]:
    raw = selector.strip()
    if not raw or ":" not in raw or raw.count(":") != 1:
        raise ValueError(f"Invalid memory selector: {selector!r}")
    address_text, size_text = raw.split(":", 1)
    address_text = address_text.strip()
    size_text = size_text.strip()
    if not address_text or not size_text:
        raise ValueError(f"Invalid memory selector: {selector!r}")
    try:
        size = int(size_text, 10)
    except ValueError as error:
        raise ValueError(f"Invalid memory selector: {selector!r}") from error
    parsed_address, parsed_size = validate_bounded_memory_read(
        address_text,
        size,
        max_bytes=max_bytes,
    )
    return address_text, parsed_address, parsed_size


def normalize_memory_selector(
    selector: str,
    *,
    max_bytes: int = MAX_FETCH_MEMORY_READ_BYTES,
) -> tuple[int, int]:
    _, parsed_address, parsed_size = parse_memory_selector(
        selector, max_bytes=max_bytes
    )
    return parsed_address, parsed_size


def collect_memory_source_from_selectors(
    selectors: list[str],
    *,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
) -> MemorySource:
    if not selectors:
        return MemorySource(embedded=False)

    requested: list[tuple[str, int, int]] = [
        parse_memory_selector(selector) for selector in selectors
    ]
    failures: list[MemoryReadEntry] = []
    entries: list[MemoryReadEntry] = []
    host = openocd_tcl_host or os.environ.get(OPENOCD_HOST_ENV, OPENOCD_DEFAULT_HOST)
    port = (
        openocd_tcl_port
        if openocd_tcl_port is not None
        else _resolve_openocd_port(os.environ.get(OPENOCD_PORT_ENV))
    )
    try:
        with OpenOcdMemoryReader(host=host, port=port) as reader:
            for address_text, address_value, size in requested:
                try:
                    payload = _read_range(
                        reader,
                        address=address_value,
                        size=size,
                    )
                    memory_snapshot = collect_gdb_memory_read(
                        address=address_text,
                        size=size,
                        data_hex=" ".join(f"{item:02x}" for item in payload),
                    )
                    entries.append(
                        MemoryReadEntry(
                            status="success",
                            address=memory_snapshot.address,
                            size=memory_snapshot.size,
                            data_hex=memory_snapshot.data_hex,
                            failure_reason=None,
                            ascii_preview="".join(
                                chr(item) if 32 <= item <= 126 else "."
                                for item in payload
                            ),
                        )
                    )
                except (RuntimeError, ValueError, OSError) as error:
                    failures.append(
                        MemoryReadEntry(
                            status="failure",
                            address=address_text,
                            size=size,
                            data_hex="",
                            failure_reason=str(error),
                            ascii_preview="",
                        )
                    )
    except OSError as error:
        failures = [
            MemoryReadEntry(
                status="failure",
                address=address_text,
                size=size,
                data_hex="",
                failure_reason=str(error),
                ascii_preview="",
            )
            for address_text, _, size in requested
        ]

    entries.extend(failures)
    entries.sort(key=_memory_entry_sort_key)
    return MemorySource(embedded=True, entries=entries)


def _read_range(
    reader: OpenOcdMemoryReader,
    *,
    address: int,
    size: int,
) -> list[int]:
    payload: list[int] = []
    remaining = size
    cursor = address
    while remaining > 0:
        chunk_size = min(MEMORY_READ_CHUNK_BYTES, remaining)
        for offset in range(chunk_size):
            raw = reader.read_memory(cursor + offset, 8)
            payload.append(_parse_hex_byte(raw))
        cursor += chunk_size
        remaining -= chunk_size
    return payload


def _parse_hex_byte(value: str) -> int:
    parsed = int(value, 0)
    if parsed < 0 or parsed > 0xFF:
        raise ValueError(f"Unexpected byte value from OpenOCD read: {value}")
    return parsed


def _memory_entry_sort_key(entry: MemoryReadEntry) -> tuple[int, int, str]:
    try:
        address_value = int(entry.address, 0)
    except ValueError:
        address_value = 0
    return (address_value, entry.size, entry.address)
