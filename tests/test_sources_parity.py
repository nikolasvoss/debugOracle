from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from debugoracle.sources.debuggers.gdb.peripheral_registers import parse_svd_definition
from debugoracle.sources.debuggers.gdb.transcript import parse_gdb_transcript
from debugoracle.sources.streams import rtt


FIXTURES = Path(__file__).parent / "fixtures"


class TranscriptParityTests(unittest.TestCase):
    def test_parse_gdb_transcript_sample_fixture_contract(self) -> None:
        transcript = parse_gdb_transcript(
            (FIXTURES / "sample.mi").read_text(encoding="utf-8"),
            now_text=lambda: "2026-03-18T10:00:00+00:00",
        )

        self.assertEqual(transcript.parse_event_counts, {"*stopped": 1, "^done": 3})
        self.assertEqual(transcript.parse_event_severity_counts, {"info": 4})
        self.assertEqual(transcript.noise_line_counts, {})
        self.assertEqual(transcript.mi_record_count, 4)
        self.assertEqual(transcript.non_mi_line_count, 0)
        self.assertEqual(transcript.mi_parse_error_count, 0)
        self.assertEqual(
            [event.kind for event in transcript.events],
            ["*stopped", "^done", "^done", "^done"],
        )
        self.assertEqual(
            transcript.latest_stop and transcript.latest_stop.get("reason"),
            "breakpoint-hit",
        )
        self.assertEqual(
            transcript.latest_registers,
            {"15": "0x08000100", "14": "0x08000081", "13": "0x20002000"},
        )
        self.assertEqual(
            [
                (entry.name, entry.value, entry.order)
                for entry in transcript.variable_evidence.locals
            ],
            [("system_state", "READY", 0), ("boot_count", "3", 1)],
        )
        self.assertEqual(transcript.variable_evidence.unknown, [])
        self.assertEqual(transcript.variable_evidence.watchpoints, [])
        self.assertEqual(transcript.parse_warnings, [])

    def test_parse_gdb_transcript_noise_and_watchpoint_contract(self) -> None:
        text = "\n".join(
            [
                "(gdb)",
                '~"hello\\n"',
                "random note",
                "^done,locals={",
                '*stopped,reason="watchpoint-trigger",wpt={exp="x"},value={old="1",new="2"},frame={addr="0x08000100",func="main",line="12"}',
                '^done,register-values=[{number="13",value="0x200"},{number="14",value="0x81"},{number="15",value="0x100"}],variables=[{name="mystery"}],locals=[{name="l0",value="7"}]',
            ]
        )
        transcript = parse_gdb_transcript(
            text, now_text=lambda: "2026-03-18T10:00:00+00:00"
        )

        self.assertEqual(
            transcript.parse_event_counts,
            {
                "prompt-marker": 1,
                "console-output": 1,
                "non_mi_line": 1,
                "mi-parse-error-known": 1,
                "*stopped": 1,
                "^done": 1,
            },
        )
        self.assertEqual(transcript.parse_event_severity_counts, {"info": 5, "warn": 1})
        self.assertEqual(
            transcript.noise_line_counts,
            {"prompt-marker": 1, "console-output": 1, "non_mi_line": 1},
        )
        self.assertEqual(transcript.mi_record_count, 2)
        self.assertEqual(transcript.non_mi_line_count, 3)
        self.assertEqual(transcript.mi_parse_error_count, 1)
        self.assertEqual(
            [event.kind for event in transcript.events],
            [
                "prompt-marker",
                "console-output",
                "non_mi_line",
                "mi-parse-error-known",
                "*stopped",
                "^done",
            ],
        )
        self.assertEqual(
            transcript.parse_warnings,
            [
                "Line 4: unable to parse MI record: Expected identifier at position 8: 'locals={'"
            ],
        )
        self.assertEqual(
            [
                (entry.name, entry.value, entry.order, entry.availability)
                for entry in transcript.variable_evidence.locals
            ],
            [("l0", "7", 0, "captured")],
        )
        self.assertEqual(
            [
                (entry.name, entry.value, entry.order, entry.availability)
                for entry in transcript.variable_evidence.unknown
            ],
            [("mystery", "<unavailable>", 1, "value-unavailable")],
        )
        self.assertEqual(
            [
                (entry.name, entry.value, entry.order, entry.availability, entry.detail)
                for entry in transcript.variable_evidence.watchpoints
            ],
            [("x", "2", 2, "captured", {"old": "1", "new": "2"})],
        )


class SvdParityTests(unittest.TestCase):
    def test_parse_svd_definition_sample_fixture_contract(self) -> None:
        definition = parse_svd_definition(str(FIXTURES / "sample.svd"))
        self.assertEqual(definition.device_name, "STM32L432KCTest")
        self.assertEqual(
            [peripheral.name for peripheral in definition.peripherals], ["GPIOA", "RCC"]
        )
        self.assertEqual(definition.peripherals[0].base_address, "0x48000000")
        self.assertEqual(
            [
                (register.name, register.address, register.width_bits, register.access)
                for register in definition.peripherals[0].registers
            ],
            [
                ("MODER", "0x48000000", 32, "read-write"),
                ("IDR", "0x48000010", 32, "read-only"),
            ],
        )

    def test_parse_svd_definition_derived_from_overlay_contract(self) -> None:
        svd_text = """
<device>
  <name>DerivedDevice</name>
  <peripherals>
    <peripheral>
      <name>BASE</name>
      <baseAddress>0x40000000</baseAddress>
      <registers>
        <register>
          <name>REG_A</name>
          <addressOffset>0x00</addressOffset>
          <size>16</size>
          <access>read-only</access>
        </register>
        <register>
          <name>REG_B</name>
          <addressOffset>0x04</addressOffset>
          <size>32</size>
          <access>write-only</access>
        </register>
      </registers>
    </peripheral>
    <peripheral derivedFrom="BASE">
      <name>CHILD</name>
      <baseAddress>0x50000000</baseAddress>
      <registers>
        <register derivedFrom="REG_A">
          <name>REG_A</name>
          <addressOffset>0x10</addressOffset>
          <access>read-write</access>
        </register>
      </registers>
    </peripheral>
  </peripherals>
</device>
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "derived.svd"
            path.write_text(svd_text, encoding="utf-8")
            definition = parse_svd_definition(str(path))

        child = definition.peripherals[1]
        self.assertEqual(child.name, "CHILD")
        self.assertEqual(child.base_address, "0x50000000")
        self.assertEqual(
            [
                (register.name, register.address, register.width_bits, register.access)
                for register in child.registers
            ],
            [
                ("REG_B", "0x50000004", 32, "write-only"),
                ("REG_A", "0x50000010", 16, "read-write"),
            ],
        )

    def test_parse_svd_definition_derived_unknown_base_error_contract(self) -> None:
        svd_text = """
<device>
  <name>BrokenDevice</name>
  <peripherals>
    <peripheral derivedFrom="MISSING_BASE">
      <name>CHILD</name>
      <baseAddress>0x50000000</baseAddress>
    </peripheral>
  </peripherals>
</device>
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "broken.svd"
            path.write_text(svd_text, encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "derives from unknown base 'MISSING_BASE'"
            ):
                parse_svd_definition(str(path))


class RttParityTests(unittest.TestCase):
    def test_capture_rtt_impl_state_sequence_to_eof(self) -> None:
        observed_statuses: list[str] = []

        def fake_write_state(_path: Path, state: rtt.RttCaptureState) -> None:
            observed_statuses.append(state.status)

        class FakeConnection:
            def __init__(self) -> None:
                self.events = [b"ABC", b""]

            def settimeout(self, _timeout: float) -> None:
                return None

            def recv(self, _size: int) -> bytes:
                return self.events.pop(0)

            def __enter__(self) -> "FakeConnection":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        class FakeSocketModule:
            timeout = TimeoutError

            @staticmethod
            def create_connection(
                _addr: tuple[str, int], timeout: float
            ) -> FakeConnection:
                return FakeConnection()

        class FakeTimeModule:
            @staticmethod
            def monotonic() -> float:
                return 0.0

            @staticmethod
            def sleep(_seconds: float) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "session.rtt"
            state_file = Path(tmpdir) / "session.rtt.state.json"
            with (
                patch(
                    "debugoracle.sources.streams.rtt._write_capture_state",
                    side_effect=fake_write_state,
                ),
                patch(
                    "debugoracle.sources.streams.rtt._utc_now",
                    side_effect=[
                        "2026-03-18T10:00:00+00:00",
                        "2026-03-18T10:00:01+00:00",
                    ],
                ),
            ):
                state = rtt.capture_rtt_impl(
                    "127.0.0.1",
                    60001,
                    out,
                    state_path=state_file,
                    socket_module=FakeSocketModule,
                    time_module=FakeTimeModule,
                )

        self.assertEqual(state.status, rtt.STATE_STATUS_EOF)
        self.assertEqual(state.bytes_captured, 3)
        self.assertEqual(
            observed_statuses, ["waiting", "connected", "connected", "eof"]
        )

    def test_capture_rtt_impl_connect_timeout_sequence(self) -> None:
        observed_statuses: list[str] = []

        def fake_write_state(_path: Path, state: rtt.RttCaptureState) -> None:
            observed_statuses.append(state.status)

        class FakeSocketModule:
            timeout = TimeoutError

            @staticmethod
            def create_connection(_addr: tuple[str, int], timeout: float) -> object:
                raise OSError("refused")

        class FakeTimeModule:
            def __init__(self) -> None:
                self._times = iter([0.0, 0.1, 0.3])

            def monotonic(self) -> float:
                return next(self._times)

            @staticmethod
            def sleep(_seconds: float) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "session.rtt"
            state_file = Path(tmpdir) / "session.rtt.state.json"
            with patch(
                "debugoracle.sources.streams.rtt._write_capture_state",
                side_effect=fake_write_state,
            ):
                with self.assertRaises(rtt.RttCaptureTimeoutError):
                    rtt.capture_rtt_impl(
                        "127.0.0.1",
                        60001,
                        out,
                        state_path=state_file,
                        connect_timeout=0.2,
                        poll_interval=0.05,
                        socket_module=FakeSocketModule,
                        time_module=FakeTimeModule(),
                    )

        self.assertEqual(observed_statuses, ["waiting", "waiting", "error"])


if __name__ == "__main__":
    unittest.main()
