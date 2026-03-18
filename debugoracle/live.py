from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .policy.halted_analysis import evaluate_halt_requirement
from .policy.limits import validate_bounded_memory_read
from .sources.debuggers.gdb.memory import collect_gdb_memory_read
from .sources.debuggers.gdb.registers import collect_gdb_registers

DEFAULT_LIVE_BACKEND = "demo"
DEFAULT_MEMORY_READ_SIZE = 16
MAX_MEMORY_READ_BYTES = 64


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class LiveResult:
    backend: str
    source: str
    timestamp: str
    available: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class LiveStatusResult(LiveResult):
    connected: bool = False
    target_state: str = "unknown"
    detail: str = ""


@dataclass
class RegisterReadResult(LiveResult):
    registers: dict[str, str] = field(default_factory=dict)


@dataclass
class MemoryReadResult(LiveResult):
    address: str | None = None
    size: int = 0
    data_hex: str = ""
    ascii_preview: str = ""


class LiveDebugBackend(ABC):
    name = "unknown"

    @abstractmethod
    def get_status(self) -> LiveStatusResult:
        raise NotImplementedError

    @abstractmethod
    def read_registers(self) -> RegisterReadResult:
        raise NotImplementedError

    @abstractmethod
    def read_memory(self, address: int, size: int) -> MemoryReadResult:
        raise NotImplementedError


class DemoLiveDebugBackend(LiveDebugBackend):
    name = "demo"
    _warning = "Demo backend provides synthetic verification data only."
    _base_address = 0x20002000
    _memory = b"DebugOracle demo memory block for read-only verification."
    _registers = {
        "pc": "0x08000100",
        "sp": "0x20002000",
        "lr": "0x08000081",
        "xpsr": "0x01000000",
        "r0": "0x00000001",
    }

    def __init__(self, *, available: bool = True, target_state: str = "stopped") -> None:
        self._available = available
        self._target_state = target_state

    def get_status(self) -> LiveStatusResult:
        if not self._available:
            return LiveStatusResult(
                backend=self.name,
                source=self.name,
                timestamp=utc_now(),
                available=False,
                warnings=[self._warning, "Demo backend is configured as unavailable."],
                connected=False,
                target_state="unavailable",
                detail="Synthetic backend disabled for this verification run.",
            )
        return LiveStatusResult(
            backend=self.name,
            source=self.name,
            timestamp=utc_now(),
            available=True,
            warnings=[self._warning],
            connected=True,
            target_state=self._target_state,
            detail="Synthetic backend ready for deterministic CLI and test verification.",
        )

    def read_registers(self) -> RegisterReadResult:
        if not self._available:
            return RegisterReadResult(
                backend=self.name,
                source=self.name,
                timestamp=utc_now(),
                available=False,
                warnings=[self._warning, "Register data is unavailable because the demo backend is disabled."],
                registers={},
            )
        halt_decision = evaluate_halt_requirement(self._target_state)
        if not halt_decision.allowed:
            return RegisterReadResult(
                backend=self.name,
                source=self.name,
                timestamp=utc_now(),
                available=False,
                warnings=[self._warning, *halt_decision.warnings],
                registers={},
            )
        return RegisterReadResult(
            backend=self.name,
            source=self.name,
            timestamp=utc_now(),
            available=True,
            warnings=[self._warning],
            registers=collect_gdb_registers(self._registers),
        )

    def read_memory(self, address: int, size: int) -> MemoryReadResult:
        if not self._available:
            return MemoryReadResult(
                backend=self.name,
                source=self.name,
                timestamp=utc_now(),
                available=False,
                warnings=[self._warning, "Memory data is unavailable because the demo backend is disabled."],
                address=_format_address(address),
                size=size,
            )
        halt_decision = evaluate_halt_requirement(self._target_state)
        if not halt_decision.allowed:
            return MemoryReadResult(
                backend=self.name,
                source=self.name,
                timestamp=utc_now(),
                available=False,
                warnings=[self._warning, *halt_decision.warnings],
                address=_format_address(address),
                size=size,
            )

        offset = address - self._base_address
        end = offset + size
        if offset < 0 or end > len(self._memory):
            return MemoryReadResult(
                backend=self.name,
                source=self.name,
                timestamp=utc_now(),
                available=False,
                warnings=[self._warning, "Requested memory range is outside the demo memory window."],
                address=_format_address(address),
                size=size,
            )

        payload = self._memory[offset:end]
        memory_snapshot = collect_gdb_memory_read(
            address=_format_address(address),
            size=size,
            data_hex=" ".join(f"{byte:02x}" for byte in payload),
        )
        return MemoryReadResult(
            backend=self.name,
            source=self.name,
            timestamp=utc_now(),
            available=True,
            warnings=[self._warning],
            address=memory_snapshot.address,
            size=memory_snapshot.size,
            data_hex=memory_snapshot.data_hex,
            ascii_preview="".join(chr(byte) if 32 <= byte <= 126 else "." for byte in payload),
        )


def build_live_backend(name: str | None = None) -> LiveDebugBackend:
    selected = (name or DEFAULT_LIVE_BACKEND).strip().lower()
    try:
        factory = _BACKEND_FACTORIES[selected]
    except KeyError as error:
        available = ", ".join(sorted(_BACKEND_FACTORIES))
        raise ValueError(f"Unknown live backend '{selected}'. Available backends: {available}.") from error
    return factory()


def available_backends() -> list[str]:
    return sorted(_BACKEND_FACTORIES)


def validate_memory_request(address: str | int, size: int) -> tuple[int, int]:
    return validate_bounded_memory_read(
        address,
        size,
        max_bytes=MAX_MEMORY_READ_BYTES,
    )


def render_live_status(result: LiveStatusResult, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(result.to_dict(), indent=2) + "\n"
    lines = [
        "DebugOracle Live Backend Status",
        "",
        f"- Backend: {result.backend}",
        f"- Source: {result.source}",
        f"- Timestamp: {result.timestamp}",
        f"- Available: {'yes' if result.available else 'no'}",
        f"- Connected: {'yes' if result.connected else 'no'}",
        f"- Target State: {result.target_state}",
        f"- Detail: {result.detail or 'unavailable'}",
        "",
        "Warnings:",
    ]
    lines.extend(_bullet_lines(result.warnings or ["None"]))
    return "\n".join(lines).rstrip() + "\n"


def render_register_result(result: RegisterReadResult, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(result.to_dict(), indent=2) + "\n"
    lines = [
        "DebugOracle Live Registers",
        "",
        f"- Backend: {result.backend}",
        f"- Source: {result.source}",
        f"- Timestamp: {result.timestamp}",
        f"- Available: {'yes' if result.available else 'no'}",
        "",
        "Registers:",
    ]
    if result.registers:
        lines.extend(_bullet_lines([f"{key}: {value}" for key, value in result.registers.items()]))
    else:
        lines.append("- None")
    lines.extend(["", "Warnings:"])
    lines.extend(_bullet_lines(result.warnings or ["None"]))
    return "\n".join(lines).rstrip() + "\n"


def render_memory_result(result: MemoryReadResult, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(result.to_dict(), indent=2) + "\n"
    lines = [
        "DebugOracle Live Memory",
        "",
        f"- Backend: {result.backend}",
        f"- Source: {result.source}",
        f"- Timestamp: {result.timestamp}",
        f"- Available: {'yes' if result.available else 'no'}",
        f"- Address: {result.address or 'unavailable'}",
        f"- Size: {result.size}",
        "",
        "Data (hex):",
        f"- {result.data_hex or 'None'}",
        "",
        "Data (ascii):",
        f"- {result.ascii_preview or 'None'}",
        "",
        "Warnings:",
    ]
    lines.extend(_bullet_lines(result.warnings or ["None"]))
    return "\n".join(lines).rstrip() + "\n"


def _format_address(address: int) -> str:
    return f"0x{address:08x}"


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


_BACKEND_FACTORIES: dict[str, Callable[[], LiveDebugBackend]] = {
    DemoLiveDebugBackend.name: DemoLiveDebugBackend,
}
