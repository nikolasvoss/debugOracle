from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Callable

from .sources.streams.rtt import (
    DEFAULT_RTT_CONNECT_TIMEOUT,
    DEFAULT_RTT_HOST,
    DEFAULT_RTT_POLL_INTERVAL,
    RTT_STREAM_SOURCE,
    STATE_SOURCE,
    STATE_STATUS_CONNECTED,
    STATE_STATUS_EOF,
    STATE_STATUS_ERROR,
    STATE_STATUS_IDLE,
    STATE_STATUS_INTERRUPTED,
    STATE_STATUS_WAITING,
    RttCaptureState,
    RttCaptureTimeoutError,
    capture_rtt_impl,
    default_state_path,
    load_capture_state,
)


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
    # Keep the legacy module as a compatibility patch surface for tests/callers
    # that monkeypatch `debugoracle.rtt.socket` or `debugoracle.rtt.time`.
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


__all__ = [
    "DEFAULT_RTT_CONNECT_TIMEOUT",
    "DEFAULT_RTT_HOST",
    "DEFAULT_RTT_POLL_INTERVAL",
    "RTT_STREAM_SOURCE",
    "STATE_SOURCE",
    "STATE_STATUS_CONNECTED",
    "STATE_STATUS_EOF",
    "STATE_STATUS_ERROR",
    "STATE_STATUS_IDLE",
    "STATE_STATUS_INTERRUPTED",
    "STATE_STATUS_WAITING",
    "RttCaptureState",
    "RttCaptureTimeoutError",
    "capture_rtt",
    "default_state_path",
    "load_capture_state",
]
