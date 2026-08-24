from __future__ import annotations

import json
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from ...safe_io import atomic_write_text, open_stream_output
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


class _StreamWriteError(OSError):
    def __init__(self, message: str, *, bytes_written: int) -> None:
        super().__init__(message)
        self.bytes_written = bytes_written


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
    workspace_root: str | Path | None = None,
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
        workspace_root=workspace_root,
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
    workspace_root: str | Path | None = None,
    socket_module: Any,
    time_module: Any,
) -> RttCaptureState:
    target = Path(output_path)
    state_target = (
        default_state_path(target) if state_path is None else Path(state_path)
    )
    waiting_state = _build_state(host=host, port=port, status=STATE_STATUS_WAITING)
    _write_capture_state(state_target, waiting_state, workspace_root=workspace_root)

    active_state = waiting_state
    connected_state = waiting_state
    try:
        connection = _wait_for_connection(
            host=host,
            port=port,
            connect_timeout=connect_timeout,
            poll_interval=poll_interval,
            waiting_state=waiting_state,
            state_target=state_target,
            socket_module=socket_module,
            time_module=time_module,
            workspace_root=workspace_root,
        )
        connected_state = _build_state(
            host=host,
            port=port,
            status=STATE_STATUS_CONNECTED,
            connected_at=_utc_now(),
        )
        active_state = connected_state
        _write_capture_state(
            state_target, connected_state, workspace_root=workspace_root
        )
        if on_connect is not None:
            on_connect(connected_state)
        connection.settimeout(max(0.05, poll_interval))

        def remember_progress(state: RttCaptureState) -> None:
            nonlocal active_state
            active_state = state

        final_state, active_state = _capture_stream_loop(
            connection=connection,
            target=target,
            state_target=state_target,
            initial_state=connected_state,
            idle_timeout=idle_timeout,
            append=append,
            socket_module=socket_module,
            time_module=time_module,
            workspace_root=workspace_root,
            on_progress=remember_progress,
        )
        return final_state
    except KeyboardInterrupt:
        interrupted_state = _state_from(
            active_state,
            status=STATE_STATUS_INTERRUPTED,
            error="interrupted",
        )
        try:
            _write_capture_state(
                state_target, interrupted_state, workspace_root=workspace_root
            )
        except OSError:
            pass
        return interrupted_state
    except OSError as error:
        error_state = _state_from(
            active_state,
            status=STATE_STATUS_ERROR,
            error=f"{error.__class__.__name__}: {error}",
        )
        try:
            _write_capture_state(
                state_target, error_state, workspace_root=workspace_root
            )
        except OSError:
            pass
        raise


def _wait_for_connection(
    *,
    host: str,
    port: int,
    connect_timeout: float,
    poll_interval: float,
    waiting_state: RttCaptureState,
    state_target: Path,
    socket_module: Any,
    time_module: Any,
    workspace_root: str | Path | None,
) -> socket.socket:
    started = time_module.monotonic()
    while True:
        try:
            return socket_module.create_connection((host, port), timeout=poll_interval)
        except OSError:
            if time_module.monotonic() - started >= max(0.0, connect_timeout):
                error_state = _build_state(
                    host=host,
                    port=port,
                    status=STATE_STATUS_ERROR,
                    error="connect_timeout",
                )
                _write_capture_state(
                    state_target, error_state, workspace_root=workspace_root
                )
                raise RttCaptureTimeoutError(
                    f"Timed out waiting for RTT server at {host}:{port}"
                ) from None
            _write_capture_state(
                state_target, waiting_state, workspace_root=workspace_root
            )
            time_module.sleep(max(0.0, poll_interval))


def _capture_stream_loop(
    *,
    connection: socket.socket,
    target: Path,
    state_target: Path,
    initial_state: RttCaptureState,
    idle_timeout: float | None,
    append: bool,
    socket_module: Any,
    time_module: Any,
    workspace_root: str | Path | None,
    on_progress: Callable[[RttCaptureState], None],
) -> tuple[RttCaptureState, RttCaptureState]:
    current_state = initial_state
    last_activity = time_module.monotonic()
    with (
        connection,
        open_stream_output(
            target,
            append=append,
            workspace_root=workspace_root,
        ) as handle,
    ):
        while True:
            try:
                chunk = connection.recv(4096)
            except socket_module.timeout:
                if (
                    idle_timeout is not None
                    and time_module.monotonic() - last_activity >= idle_timeout
                ):
                    idle_state = _state_from(current_state, status=STATE_STATUS_IDLE)
                    _write_capture_state(
                        state_target, idle_state, workspace_root=workspace_root
                    )
                    return idle_state, current_state
                continue

            if not chunk:
                eof_state = _state_from(current_state, status=STATE_STATUS_EOF)
                _write_capture_state(
                    state_target, eof_state, workspace_root=workspace_root
                )
                return eof_state, current_state

            try:
                written = _write_stream_chunk(handle, chunk)
            except _StreamWriteError as error:
                if error.bytes_written:
                    current_state = _state_from(
                        current_state,
                        status=STATE_STATUS_CONNECTED,
                        last_byte_at=_utc_now(),
                        bytes_captured=(
                            current_state.bytes_captured + error.bytes_written
                        ),
                    )
                    on_progress(current_state)
                raise
            handle.flush()
            last_activity = time_module.monotonic()
            current_state = _state_from(
                current_state,
                status=STATE_STATUS_CONNECTED,
                last_byte_at=_utc_now(),
                bytes_captured=current_state.bytes_captured + written,
            )
            on_progress(current_state)
            _write_capture_state(
                state_target, current_state, workspace_root=workspace_root
            )


def _write_stream_chunk(handle: BinaryIO, chunk: bytes) -> int:
    view = memoryview(chunk)
    written = 0
    while written < len(view):
        try:
            count = handle.write(view[written:])
        except OSError as error:
            raise _StreamWriteError(
                f"RTT output write failed after {written} bytes: {error}",
                bytes_written=written,
            ) from error
        if count is None or count <= 0:
            raise _StreamWriteError(
                f"RTT output write made no progress after {written} bytes.",
                bytes_written=written,
            )
        written += count
    return written


def _build_state(
    *,
    host: str,
    port: int,
    status: str,
    connected_at: str | None = None,
    last_byte_at: str | None = None,
    bytes_captured: int = 0,
    error: str | None = None,
) -> RttCaptureState:
    return RttCaptureState(
        source=STATE_SOURCE,
        host=host,
        port=port,
        status=status,
        connected_at=connected_at,
        last_byte_at=last_byte_at,
        bytes_captured=bytes_captured,
        error=error,
    )


def _state_from(
    current: RttCaptureState,
    *,
    status: str,
    last_byte_at: str | None = None,
    bytes_captured: int | None = None,
    error: str | None = None,
) -> RttCaptureState:
    return _build_state(
        host=current.host,
        port=current.port,
        status=status,
        connected_at=current.connected_at,
        last_byte_at=current.last_byte_at if last_byte_at is None else last_byte_at,
        bytes_captured=current.bytes_captured
        if bytes_captured is None
        else bytes_captured,
        error=error,
    )


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


def _write_capture_state(
    path: Path,
    state: RttCaptureState,
    *,
    workspace_root: str | Path | None,
) -> None:
    atomic_write_text(
        path,
        json.dumps(state.to_dict(), indent=2) + "\n",
        workspace_root=workspace_root,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
