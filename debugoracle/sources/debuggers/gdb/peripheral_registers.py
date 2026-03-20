from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from ....artifacts.models import PeripheralRegisterSet, RegisterEntry, RegisterSource
from ...base import SourceDescriptor, validate_source_descriptor

GDB_PERIPHERAL_REGISTERS_SOURCE = validate_source_descriptor(
    SourceDescriptor(
        source_id="gdb_peripheral_registers",
        family="snapshot",
        trigger="on_halt",
        requires_halt=True,
        persistence_default="artifact",
        backend_dependency="gdb+svd",
        supports_parsing=True,
        supports_reduction=True,
    )
)


@dataclass(frozen=True)
class SvdDeviceDefinition:
    device_name: str
    peripherals: list[PeripheralRegisterSet]


def collect_peripheral_registers_from_svd(svd_file: str) -> RegisterSource:
    definition = parse_svd_definition(svd_file)
    peripheral_count = len(definition.peripherals)
    register_count = sum(len(peripheral.registers) for peripheral in definition.peripherals)
    return RegisterSource(
        embedded=True,
        svd_source=str(Path(svd_file).resolve()),
        device_name=definition.device_name,
        peripheral_count=peripheral_count,
        register_count=register_count,
        success_count=0,
        failure_count=0,
        skipped_count=register_count,
        peripherals=definition.peripherals,
    )


def parse_svd_definition(svd_file: str) -> SvdDeviceDefinition:
    path = Path(svd_file)
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError as error:
        raise ValueError(f"Could not parse SVD XML: {error}") from error
    except OSError as error:
        raise ValueError(f"Could not read SVD file '{svd_file}': {error}") from error

    device_name = _text(root.find("name")) or path.stem
    peripherals_node = root.find("peripherals")
    if peripherals_node is None:
        raise ValueError("SVD file did not contain any peripherals")

    peripherals: list[PeripheralRegisterSet] = []
    for peripheral_node in peripherals_node.findall("peripheral"):
        peripheral_name = _text(peripheral_node.find("name"))
        base_address_text = _text(peripheral_node.find("baseAddress"))
        if peripheral_name is None or base_address_text is None:
            continue
        registers_node = peripheral_node.find("registers")
        registers: list[RegisterEntry] = []
        if registers_node is not None:
            for register_node in registers_node.findall("register"):
                register_name = _text(register_node.find("name"))
                offset_text = _text(register_node.find("addressOffset"))
                size_text = _text(register_node.find("size"))
                if register_name is None or offset_text is None:
                    continue
                offset = _parse_int(offset_text)
                base_address = _parse_int(base_address_text)
                width_bits = _parse_int(size_text) if size_text is not None else 32
                registers.append(
                    RegisterEntry(
                        name=register_name,
                        address=_hex(base_address + offset),
                        width_bits=width_bits,
                        read_status="skipped",
                        skip_reason="Peripheral register capture backend is not available in file-based fetch yet.",
                        access=_text(register_node.find("access")),
                    )
                )
        peripherals.append(
            PeripheralRegisterSet(
                name=peripheral_name,
                base_address=_hex(_parse_int(base_address_text)),
                registers=registers,
            )
        )

    if not peripherals:
        raise ValueError("SVD file did not contain any usable peripheral definitions")
    return SvdDeviceDefinition(device_name=device_name, peripherals=peripherals)


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    text = node.text.strip()
    return text or None


def _parse_int(text: str) -> int:
    value = text.strip().lower()
    return int(value, 16 if value.startswith("0x") else 10)


def _hex(value: int) -> str:
    return f"0x{value:08x}"
