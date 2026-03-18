from __future__ import annotations

import json
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..base import SourceDescriptor, validate_source_descriptor

DEFAULT_RTT_HOST = "127.0.0.1"
DEFAULT_RTT_CONNECT_TIMEOUT = 10.0
DEFAULT_RTT_POLL_INTERVAL = 0.2
STATE_SOURCE = "openocd-rtt-tcp"
STATE_STATUS_WAITING = "waiting"
STATE_STATUS_CONNECTED = "connected"
STATE_STATUS_IDLE = "idle"
STATE_STATUS_EOF = "eof"
STATE_STATUS_INTERRUPTED = "interrupted"
STATE_STATUS_ERROR = "error"

RTT_STREAM_SOURCE = validate_source_descriptor(
    SourceDescriptor(
        source_id="rtt",
        family="stream",
        trigger="passive",
        requires_halt=False,
        persistence_default="raw_sidecar",
        backend_dependency="openocd-rtt-tcp",
        supports_parsing=False,
        supports_reduction=False,
    )
)


class RttCaptureTimeoutError(RuntimeError):
    """Raised when the RTT TCP server never becomes reachable."""


@dataclass(frozen=True)
class RttCaptureState:
    source: str
    host: str
    port: int
    status: str
    connected_at: str | None = None
    last_byte_at: str | None = None
    bytes_captured: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def capture_rtt(
    host: str,
    port: int,
    output_path: str | Path,
    *,
    state_path: str | Path | None = None,
    connect_timeout: float = DEFAULT_RTT_CONNECT_TIMEOUT,
    poll_interval: float = DEFAULT_RTT_POLL_INTERVAL,
    idle_timeout: float | None = None,
    append: bool = False,
    on_connect: Callable[[RttCaptureState], None] | None = None,
) -> RttCaptureState:
    return capture_rtt_impl(
        host,
        port,
        output_path,
        state_path=state_path,
        connect_timeout=connect_timeout,
        poll_interval=poll_interval,
        idle_timeout=idle_timeout,
        append=append,
        on_connect=on_connect,
        socket_module=socket,
        time_module=time,
    )


def capture_rtt_impl(
    host: str,
    port: int,
    output_path: str | Path,
    *,
    state_path: str | Path | None = None,
    connect_timeout: float = DEFAULT_RTT_CONNECT_TIMEOUT,
    poll_interval: float = DEFAULT_RTT_POLL_INTERVAL,
    idle_timeout: float | None = None,
    append: bool = False,
    on_connect: Callable[[RttCaptureState], None] | None = None,
    socket_module: object,
    time_module: object,
) -> RttCaptureState:
    target = Path(output_path)
    state_target = default_state_path(target) if state_path is None else Path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    state_target.parent.mkdir(parents=True, exist_ok=True)

    started = time_module.monotonic()
    waiting_state = RttCaptureState(
        source=STATE_SOURCE,
        host=host,
        port=port,
        status=STATE_STATUS_WAITING,
    )
    _write_capture_state(state_target, waiting_state)

    active_state = waiting_state
    connected_state = waiting_state
    connection: socket.socket | None = None
    try:
        while connection is None:
            try:
                connection = socket_module.create_connection((host, port), timeout=poll_interval)
            except OSError:
                if time_module.monotonic() - started >= max(0.0, connect_timeout):
                    error_state = RttCaptureState(
                        source=STATE_SOURCE,
                        host=host,
                        port=port,
                        status=STATE_STATUS_ERROR,
                        error="connect_timeout",
                    )
                    _write_capture_state(state_target, error_state)
                    raise RttCaptureTimeoutError(
                        f"Timed out waiting for RTT server at {host}:{port}"
                    ) from None
                _write_capture_state(state_target, waiting_state)
                time_module.sleep(max(0.0, poll_interval))

        connected_at = _utc_now()
        connected_state = RttCaptureState(
            source=STATE_SOURCE,
            host=host,
            port=port,
            status=STATE_STATUS_CONNECTED,
            connected_at=connected_at,
        )
        active_state = connected_state
        _write_capture_state(state_target, connected_state)
        if on_connect is not None:
            on_connect(connected_state)
        connection.settimeout(max(0.05, poll_interval))

        last_activity = time_module.monotonic()
        write_mode = "ab" if append else "wb"
        with connection, target.open(write_mode) as handle:
            while True:
                try:
                    chunk = connection.recv(4096)
                except socket_module.timeout:
                    if idle_timeout is not None and time_module.monotonic() - last_activity >= idle_timeout:
                        idle_state = RttCaptureState(
                            source=STATE_SOURCE,
                            host=host,
                            port=port,
                            status=STATE_STATUS_IDLE,
                            connected_at=connected_state.connected_at,
                            last_byte_at=connected_state.last_byte_at,
                            bytes_captured=connected_state.bytes_captured,
                        )
                        _write_capture_state(state_target, idle_state)
                        return idle_state
                    continue

                if not chunk:
                    eof_state = RttCaptureState(
                        source=STATE_SOURCE,
                        host=host,
                        port=port,
                        status=STATE_STATUS_EOF,
                        connected_at=connected_state.connected_at,
                        last_byte_at=connected_state.last_byte_at,
                        bytes_captured=connected_state.bytes_captured,
                    )
                    _write_capture_state(state_target, eof_state)
                    return eof_state

                handle.write(chunk)
                handle.flush()
                last_activity = time_module.monotonic()
                connected_state = RttCaptureState(
                    source=STATE_SOURCE,
                    host=host,
                    port=port,
                    status=STATE_STATUS_CONNECTED,
                    connected_at=connected_state.connected_at,
                    last_byte_at=_utc_now(),
                    bytes_captured=connected_state.bytes_captured + len(chunk),
                )
                active_state = connected_state
                _write_capture_state(state_target, connected_state)
    except KeyboardInterrupt:
        interrupted_state = RttCaptureState(
            source=STATE_SOURCE,
            host=host,
            port=port,
            status=STATE_STATUS_INTERRUPTED,
            connected_at=active_state.connected_at,
            last_byte_at=active_state.last_byte_at,
            bytes_captured=active_state.bytes_captured,
            error="interrupted",
        )
        try:
            _write_capture_state(state_target, interrupted_state)
        except OSError:
            pass
        return interrupted_state
    except OSError as error:
        error_state = RttCaptureState(
            source=STATE_SOURCE,
            host=host,
            port=port,
            status=STATE_STATUS_ERROR,
            connected_at=connected_state.connected_at,
            last_byte_at=connected_state.last_byte_at,
            bytes_captured=connected_state.bytes_captured,
            error=f"{error.__class__.__name__}: {error}",
        )
        try:
            _write_capture_state(state_target, error_state)
        except OSError:
            pass
        raise


def default_state_path(output_path: str | Path) -> Path:
    path = Path(output_path)
    return path.parent / f"{path.name}.state.json"


def load_capture_state(path: str | Path) -> RttCaptureState:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return RttCaptureState(
        source=str(data["source"]),
        host=str(data["host"]),
        port=int(data["port"]),
        status=str(data["status"]),
        connected_at=_optional_text(data.get("connected_at")),
        last_byte_at=_optional_text(data.get("last_byte_at")),
        bytes_captured=int(data.get("bytes_captured", 0)),
        error=_optional_text(data.get("error")),
    )


def _write_capture_state(path: Path, state: RttCaptureState) -> None:
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
