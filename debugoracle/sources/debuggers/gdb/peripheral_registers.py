from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

from ....artifacts.models import PeripheralRegisterSet, RegisterEntry, RegisterSource
from ....openocd import OpenOcdReachabilityError
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

OPENOCD_DEFAULT_HOST = "127.0.0.1"
OPENOCD_DEFAULT_PORT = 6666
OPENOCD_HOST_ENV = "DEBUGORACLE_OPENOCD_HOST"
OPENOCD_PORT_ENV = "DEBUGORACLE_OPENOCD_PORT"
OPENOCD_SOCKET_TIMEOUT_SECONDS = 1.0
OPENOCD_TCL_TERMINATOR = b"\x1a"
OPENOCD_MAX_RESPONSE_BYTES = 16 * 1024
MI_HALT_TAIL_LINE_COUNT = 50
SAFE_READ_ACCESS_MODES = {"read-only", "read-write"}
MI_STATE_STOPPED = "stopped"
MI_STATE_RUNNING = "running"


@dataclass(frozen=True)
class SvdDeviceDefinition:
    device_name: str
    svd_source: str
    peripherals: list[PeripheralRegisterSet]


class OpenOcdMemoryReader:
    def __init__(
        self,
        host: str = OPENOCD_DEFAULT_HOST,
        port: int = OPENOCD_DEFAULT_PORT,
        *,
        timeout_seconds: float = OPENOCD_SOCKET_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._socket: socket.socket | None = None

    def __enter__(self) -> "OpenOcdMemoryReader":
        self._socket = socket.create_connection(
            (self._host, self._port),
            timeout=self._timeout_seconds,
        )
        self._socket.settimeout(self._timeout_seconds)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def read_memory(self, address: int, width_bits: int) -> str:
        if self._socket is None:
            raise RuntimeError("OpenOCD reader is not connected")
        command = f"read_memory 0x{address:08x} {width_bits} 1".encode("utf-8")
        self._socket.sendall(command + OPENOCD_TCL_TERMINATOR)
        response = self._read_response()
        return _normalize_value_hex(response, width_bits)

    def _read_response(self) -> str:
        if self._socket is None:
            raise RuntimeError("OpenOCD reader is not connected")
        buffer = bytearray()
        while True:
            try:
                chunk = self._socket.recv(4096)
            except socket.timeout as error:
                raise OSError("Timed out waiting for an OpenOCD Tcl response terminator.") from error
            if not chunk:
                raise OSError("OpenOCD closed the connection")
            buffer.extend(chunk)
            if OPENOCD_TCL_TERMINATOR in buffer:
                raw, _, _ = buffer.partition(OPENOCD_TCL_TERMINATOR)
                return raw.decode("utf-8", errors="replace").strip()
            if len(buffer) > OPENOCD_MAX_RESPONSE_BYTES:
                raise ValueError(
                    "OpenOCD response exceeded the safe size limit without a Tcl terminator. "
                    "Check that --openocd-tcl-port points to the OpenOCD Tcl endpoint."
                )


def collect_peripheral_registers_from_svd(svd_file: str) -> RegisterSource:
    definition = parse_svd_definition(svd_file)
    return _build_register_source(definition)


def capture_peripheral_registers_from_svd(
    svd_file: str,
    *,
    mi_text: str,
    openocd_tcl_host: str | None = None,
    openocd_tcl_port: int | None = None,
) -> RegisterSource:
    _require_recent_halt(mi_text)

    definition = parse_svd_definition(svd_file)
    source = _build_register_source(definition)
    safe_targets = _safe_targets(source)
    if not safe_targets:
        raise ValueError("Peripheral capture did not find any safe-readable registers in the supplied SVD.")

    host = openocd_tcl_host or os.environ.get(OPENOCD_HOST_ENV, OPENOCD_DEFAULT_HOST)
    port = openocd_tcl_port if openocd_tcl_port is not None else _resolve_openocd_port(os.environ.get(OPENOCD_PORT_ENV))

    try:
        with OpenOcdMemoryReader(host=host, port=port) as reader:
            for register in safe_targets:
                try:
                    register.value_hex = reader.read_memory(_parse_int(register.address), register.width_bits)
                    register.read_status = "success"
                    register.failure_reason = None
                    register.skip_reason = None
                except (OSError, ValueError) as error:
                    register.read_status = "failure"
                    register.failure_reason = str(error)
                    register.skip_reason = None
    except OSError as error:
        raise OpenOcdReachabilityError(host=host, port=port, detail=str(error)) from error

    _update_counts(source)
    if source.success_count == 0:
        raise ValueError("Peripheral capture did not read any register values successfully.")
    return source


def parse_svd_definition(svd_file: str) -> SvdDeviceDefinition:
    path = Path(svd_file)
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError as error:
        raise ValueError(f"Could not parse SVD XML: {error}") from error
    except OSError as error:
        raise ValueError(f"Could not read SVD file '{svd_file}': {error}") from error

    device_name = _text(root.find("name")) or path.stem
    peripheral_lookup, peripheral_nodes = _load_peripheral_index(root)
    peripherals = _collect_peripheral_sets(peripheral_nodes, peripheral_lookup)

    if not peripherals:
        raise ValueError("SVD file did not contain any usable peripheral definitions")
    return SvdDeviceDefinition(
        device_name=device_name,
        svd_source=str(path.resolve()),
        peripherals=peripherals,
    )


def _load_peripheral_index(root: ET.Element) -> tuple[dict[str, ET.Element], list[ET.Element]]:
    peripherals_node = root.find("peripherals")
    if peripherals_node is None:
        raise ValueError("SVD file did not contain any peripherals")
    peripheral_nodes = peripherals_node.findall("peripheral")
    peripheral_lookup: dict[str, ET.Element] = {}
    for peripheral_node in peripheral_nodes:
        peripheral_name = _text(peripheral_node.find("name"))
        if peripheral_name:
            peripheral_lookup[peripheral_name] = peripheral_node
    return peripheral_lookup, peripheral_nodes


def _collect_peripheral_sets(
    peripheral_nodes: list[ET.Element],
    peripheral_lookup: dict[str, ET.Element],
) -> list[PeripheralRegisterSet]:
    peripherals: list[PeripheralRegisterSet] = []
    for peripheral_node in peripheral_nodes:
        resolved_peripheral = _resolve_peripheral_node(peripheral_node, peripheral_lookup, seen=set())
        peripheral = _build_peripheral_register_set(resolved_peripheral)
        if peripheral is not None:
            peripherals.append(peripheral)
    return peripherals


def _build_peripheral_register_set(resolved_peripheral: ET.Element) -> PeripheralRegisterSet | None:
    peripheral_name = _text(resolved_peripheral.find("name"))
    base_address_text = _text(resolved_peripheral.find("baseAddress"))
    if peripheral_name is None or base_address_text is None:
        return None
    base_address = _parse_int(base_address_text)
    registers_node = resolved_peripheral.find("registers")
    registers = _build_register_entries(registers_node, base_address)
    return PeripheralRegisterSet(
        name=peripheral_name,
        base_address=_hex(base_address),
        registers=registers,
    )


def _build_register_entries(registers_node: ET.Element | None, base_address: int) -> list[RegisterEntry]:
    if registers_node is None:
        return []
    registers: list[RegisterEntry] = []
    for register_node in registers_node.findall("register"):
        register = _build_register_entry(register_node, base_address)
        if register is not None:
            registers.append(register)
    return registers


def _build_register_entry(register_node: ET.Element, base_address: int) -> RegisterEntry | None:
    register_name = _text(register_node.find("name"))
    offset_text = _text(register_node.find("addressOffset"))
    size_text = _text(register_node.find("size"))
    if register_name is None or offset_text is None:
        return None
    offset = _parse_int(offset_text)
    width_bits = _parse_int(size_text) if size_text is not None else 32
    return RegisterEntry(
        name=register_name,
        address=_hex(base_address + offset),
        width_bits=width_bits,
        read_status="skipped",
        skip_reason="Peripheral register capture is unavailable for this register.",
        access=_text(register_node.find("access")),
    )


def _build_register_source(definition: SvdDeviceDefinition) -> RegisterSource:
    peripheral_count = len(definition.peripherals)
    register_count = sum(len(peripheral.registers) for peripheral in definition.peripherals)
    source = RegisterSource(
        embedded=True,
        svd_source=definition.svd_source,
        device_name=definition.device_name,
        peripheral_count=peripheral_count,
        register_count=register_count,
        success_count=0,
        failure_count=0,
        skipped_count=register_count,
        peripherals=definition.peripherals,
    )
    _apply_safe_read_policy(source)
    _update_counts(source)
    return source


def _apply_safe_read_policy(source: RegisterSource) -> None:
    for peripheral in source.peripherals:
        for register in peripheral.registers:
            access_mode = _normalized_access(register.access)
            if access_mode in SAFE_READ_ACCESS_MODES:
                register.read_status = "skipped"
                register.skip_reason = "Waiting for live peripheral capture."
                continue
            register.read_status = "skipped"
            register.skip_reason = _skip_reason_for_access(access_mode)


def _safe_targets(source: RegisterSource) -> list[RegisterEntry]:
    targets: list[RegisterEntry] = []
    for peripheral in source.peripherals:
        for register in peripheral.registers:
            if _normalized_access(register.access) in SAFE_READ_ACCESS_MODES:
                targets.append(register)
    return targets


def _update_counts(source: RegisterSource) -> None:
    success_count = 0
    failure_count = 0
    skipped_count = 0
    register_count = 0
    for peripheral in source.peripherals:
        for register in peripheral.registers:
            register_count += 1
            if register.read_status == "success":
                success_count += 1
            elif register.read_status == "failure":
                failure_count += 1
            else:
                skipped_count += 1
    source.register_count = register_count
    source.success_count = success_count
    source.failure_count = failure_count
    source.skipped_count = skipped_count


def _require_recent_halt(mi_text: str) -> None:
    latest_state = _latest_mi_target_state(mi_text)
    if latest_state != MI_STATE_STOPPED:
        raise ValueError("Peripheral capture requires a recent halted target in the GDB/MI log.")


def _latest_mi_target_state(mi_text: str) -> str | None:
    lines = [line for line in mi_text.splitlines() if line.strip()]
    latest_state: str | None = None
    for line in lines[-MI_HALT_TAIL_LINE_COUNT:]:
        cleaned = _strip_mi_token(line)
        if cleaned.startswith("*stopped"):
            latest_state = MI_STATE_STOPPED
        elif cleaned.startswith("*running") or cleaned.startswith("^running"):
            latest_state = MI_STATE_RUNNING
    return latest_state


def _strip_mi_token(line: str) -> str:
    cleaned = line.lstrip()
    while cleaned[:1].isdigit():
        cleaned = cleaned[1:]
    return cleaned.lstrip()


def _resolve_openocd_port(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return OPENOCD_DEFAULT_PORT
    try:
        return int(raw, 10)
    except ValueError as error:
        raise ValueError(f"Invalid OpenOCD port in {OPENOCD_PORT_ENV}: {raw}") from error


def _normalize_value_hex(raw_value: str, width_bits: int) -> str:
    token = raw_value.strip().strip("{}").split()[0]
    try:
        value = int(token, 0)
    except (IndexError, ValueError) as error:
        raise ValueError(f"Unexpected OpenOCD read response: {raw_value}") from error
    digits = max(1, width_bits // 4)
    return f"0x{value:0{digits}x}"


def _normalized_access(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lower() or None


def _skip_reason_for_access(access_mode: str | None) -> str:
    if access_mode is None:
        return "Skipped because access metadata is missing."
    if access_mode == "write-only":
        return "Skipped because write-only registers are not safe to read."
    return f"Skipped because access mode '{access_mode}' is not supported for safe reads."


def _resolve_peripheral_node(
    peripheral_node: ET.Element,
    peripheral_lookup: dict[str, ET.Element],
    *,
    seen: set[str],
) -> ET.Element:
    derived_from = peripheral_node.get("derivedFrom")
    if not derived_from:
        return deepcopy(peripheral_node)
    if derived_from in seen:
        raise ValueError(f"SVD peripheral inheritance cycle detected for '{derived_from}'")
    base_node = peripheral_lookup.get(derived_from)
    if base_node is None:
        raise ValueError(f"SVD peripheral '{_text(peripheral_node.find('name')) or '<unnamed>'}' derives from unknown base '{derived_from}'")

    merged = _resolve_peripheral_node(base_node, peripheral_lookup, seen=seen | {derived_from})
    _overlay_text_child(merged, peripheral_node, "name")
    _overlay_text_child(merged, peripheral_node, "baseAddress")
    _merge_register_nodes(merged, peripheral_node)
    return merged


def _merge_register_nodes(target_peripheral: ET.Element, override_peripheral: ET.Element) -> None:
    override_registers = override_peripheral.find("registers")
    if override_registers is None:
        return

    target_registers = target_peripheral.find("registers")
    if target_registers is None:
        target_registers = ET.SubElement(target_peripheral, "registers")

    register_lookup: dict[str, ET.Element] = {}
    for register_node in target_registers.findall("register"):
        register_name = _text(register_node.find("name"))
        if register_name:
            register_lookup[register_name] = register_node

    for override_register in override_registers.findall("register"):
        resolved_register = _resolve_register_node(override_register, register_lookup, seen=set())
        register_name = _text(resolved_register.find("name"))
        if register_name is None:
            continue
        existing = register_lookup.get(register_name)
        if existing is not None:
            target_registers.remove(existing)
        target_registers.append(resolved_register)
        register_lookup[register_name] = resolved_register


def _resolve_register_node(
    register_node: ET.Element,
    register_lookup: dict[str, ET.Element],
    *,
    seen: set[str],
) -> ET.Element:
    derived_from = register_node.get("derivedFrom")
    if not derived_from:
        return deepcopy(register_node)
    if derived_from in seen:
        raise ValueError(f"SVD register inheritance cycle detected for '{derived_from}'")
    base_node = register_lookup.get(derived_from)
    if base_node is None:
        raise ValueError(f"SVD register '{_text(register_node.find('name')) or '<unnamed>'}' derives from unknown base '{derived_from}'")

    merged = _resolve_register_node(base_node, register_lookup, seen=seen | {derived_from})
    for tag_name in ("name", "addressOffset", "size", "access"):
        _overlay_text_child(merged, register_node, tag_name)
    return merged


def _overlay_text_child(target: ET.Element, override: ET.Element, tag_name: str) -> None:
    override_node = override.find(tag_name)
    if override_node is None or override_node.text is None:
        return
    target_node = target.find(tag_name)
    if target_node is None:
        target_node = ET.SubElement(target, tag_name)
    target_node.text = override_node.text


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
