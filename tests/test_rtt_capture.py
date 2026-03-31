from __future__ import annotations

import io
import json
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from debugoracle.cli import main
from debugoracle.rtt import (
    STATE_STATUS_INTERRUPTED,
    RttCaptureTimeoutError,
    capture_rtt,
    load_capture_state,
)
from debugoracle.sources.streams.rtt import (
    RTT_STREAM_SOURCE as CANONICAL_RTT_STREAM_SOURCE,
)


class RttCaptureTests(unittest.TestCase):
    def test_canonical_rtt_source_module_exports_stream_descriptor(self) -> None:
        self.assertEqual(CANONICAL_RTT_STREAM_SOURCE.source_id, "rtt")
        self.assertEqual(CANONICAL_RTT_STREAM_SOURCE.family, "stream")

    def test_capture_rtt_waits_for_server_and_writes_stream(self) -> None:
        payload = b"RECOVERY requested err=0x02\nSTATE BOOT -> FAULT_RECOVERY\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            fake_connection = _FakeConnection([payload, b""])
            with (
                patch(
                    "debugoracle.rtt.socket.create_connection",
                    side_effect=[
                        OSError("refused"),
                        OSError("refused"),
                        fake_connection,
                    ],
                ),
                patch(
                    "debugoracle.rtt.time.monotonic",
                    side_effect=[0.0, 0.1, 0.2, 0.25, 0.3],
                ),
                patch("debugoracle.rtt.time.sleep"),
            ):
                state = capture_rtt(
                    "127.0.0.1",
                    60001,
                    output,
                    connect_timeout=1.0,
                    poll_interval=0.05,
                )

            self.assertEqual(state.status, "eof")
            self.assertEqual(state.bytes_captured, len(payload))
            self.assertEqual(output.read_bytes(), payload)
            loaded = load_capture_state(f"{output}.state.json")
            self.assertEqual(loaded.status, "eof")
            self.assertEqual(loaded.bytes_captured, len(payload))

    def test_capture_rtt_records_idle_when_connected_without_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            fake_connection = _FakeConnection([socket.timeout()])
            with (
                patch(
                    "debugoracle.rtt.socket.create_connection",
                    return_value=fake_connection,
                ),
                patch(
                    "debugoracle.rtt.time.monotonic",
                    side_effect=[0.0, 0.0, 0.2],
                ),
            ):
                state = capture_rtt(
                    "127.0.0.1",
                    60001,
                    output,
                    connect_timeout=0.5,
                    poll_interval=0.05,
                    idle_timeout=0.1,
                )

            self.assertEqual(state.status, "idle")
            self.assertEqual(state.bytes_captured, 0)
            self.assertEqual(output.read_bytes(), b"")
            loaded = load_capture_state(f"{output}.state.json")
            self.assertEqual(loaded.status, "idle")
            self.assertEqual(loaded.bytes_captured, 0)

    def test_capture_rtt_records_connect_timeout_in_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            with (
                patch(
                    "debugoracle.rtt.socket.create_connection",
                    side_effect=OSError("refused"),
                ),
                patch(
                    "debugoracle.rtt.time.monotonic",
                    side_effect=[0.0, 0.1, 0.21],
                ),
                patch("debugoracle.rtt.time.sleep"),
            ):
                with self.assertRaises(RttCaptureTimeoutError):
                    capture_rtt(
                        "127.0.0.1",
                        60001,
                        output,
                        connect_timeout=0.2,
                        poll_interval=0.05,
                    )

            payload = json.loads(
                (Path(f"{output}.state.json")).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"], "connect_timeout")

    def test_capture_rtt_records_error_state_when_output_is_unwritable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "not-a-file"
            output.mkdir()
            state_path = Path(tmpdir) / "session.rtt.state.json"
            with patch(
                "debugoracle.rtt.socket.create_connection",
                return_value=_FakeConnection([]),
            ):
                with self.assertRaises(OSError):
                    capture_rtt(
                        "127.0.0.1",
                        60001,
                        output,
                        state_path=state_path,
                        connect_timeout=0.5,
                        poll_interval=0.05,
                    )

            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "error")
            self.assertIn("IsADirectoryError", payload["error"])

    def test_capture_rtt_cli_reports_connection_and_writes_output(self) -> None:
        payload = b"STAT t=1014 loop=6 state=BOOT\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            buffer = io.StringIO()
            with (
                patch(
                    "debugoracle.rtt.socket.create_connection",
                    return_value=_FakeConnection([payload, b""]),
                ),
                redirect_stdout(buffer),
            ):
                exit_code = main(
                    [
                        "capture-rtt",
                        "--port",
                        "60001",
                        "--output",
                        str(output),
                        "--connect-timeout",
                        "0.5",
                        "--poll-interval",
                        "0.05",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(output.read_bytes(), payload)
            stdout = buffer.getvalue()
            self.assertIn(f"RTT capture connected 127.0.0.1:60001 -> {output}", stdout)
            self.assertIn(
                "RTT capture stopped because the RTT server closed the connection.",
                stdout,
            )

    def test_capture_rtt_keyboard_interrupt_is_graceful_and_updates_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "session.rtt"
            state_path = output.with_suffix(".rtt.state.json")
            with patch(
                "debugoracle.rtt.socket.create_connection",
                return_value=_FakeConnection([KeyboardInterrupt()]),
            ):
                state = capture_rtt(
                    "127.0.0.1",
                    60001,
                    output,
                    connect_timeout=0.5,
                    poll_interval=0.05,
                    state_path=state_path,
                )

            self.assertEqual(state.status, STATE_STATUS_INTERRUPTED)
            self.assertEqual(state.error, "interrupted")
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["status"], STATE_STATUS_INTERRUPTED)
            self.assertEqual(loaded["error"], "interrupted")
            self.assertEqual(output.read_bytes(), b"")


class _FakeConnection:
    def __init__(self, events: list[bytes | BaseException]) -> None:
        self._events = list(events)
        self.timeout: float | None = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv(self, _: int) -> bytes:
        if not self._events:
            return b""
        event = self._events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
