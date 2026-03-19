from __future__ import annotations

import unittest

from debugoracle.builder import GDB_HALT_SNAPSHOT_SOURCE, GDB_TRANSCRIPT_SOURCE
from debugoracle.artifacts.models import VariableEntry, VariableEvidence
from debugoracle.rtt import RTT_STREAM_SOURCE
from debugoracle.sources.base import SourceDescriptor
from debugoracle.sources.debuggers.gdb.halt_snapshot import (
    GDB_HALT_SNAPSHOT_SOURCE as CANONICAL_GDB_HALT_SNAPSHOT_SOURCE,
    build_halt_snapshot,
)
from debugoracle.sources.debuggers.gdb.memory import (
    GDB_MEMORY_SOURCE as CANONICAL_GDB_MEMORY_SOURCE,
    collect_gdb_memory_read,
)
from debugoracle.sources.debuggers.gdb.registers import (
    GDB_REGISTERS_SOURCE as CANONICAL_GDB_REGISTERS_SOURCE,
    collect_gdb_registers,
)
from debugoracle.sources.debuggers.gdb.transcript import (
    GDB_TRANSCRIPT_SOURCE as CANONICAL_GDB_TRANSCRIPT_SOURCE,
)


class SourceContractTests(unittest.TestCase):
    def test_rtt_exposes_stream_source_descriptor_metadata(self) -> None:
        self.assertIsInstance(RTT_STREAM_SOURCE, SourceDescriptor)
        self.assertEqual(RTT_STREAM_SOURCE.source_id, "rtt")
        self.assertEqual(RTT_STREAM_SOURCE.family, "stream")
        self.assertEqual(RTT_STREAM_SOURCE.trigger, "passive")
        self.assertFalse(RTT_STREAM_SOURCE.requires_halt)
        self.assertEqual(RTT_STREAM_SOURCE.persistence_default, "raw_sidecar")
        self.assertEqual(RTT_STREAM_SOURCE.backend_dependency, "openocd-rtt-tcp")
        self.assertFalse(RTT_STREAM_SOURCE.supports_parsing)
        self.assertFalse(RTT_STREAM_SOURCE.supports_reduction)

    def test_builder_exposes_gdb_stream_and_snapshot_source_descriptors(self) -> None:
        self.assertIsInstance(GDB_TRANSCRIPT_SOURCE, SourceDescriptor)
        self.assertEqual(GDB_TRANSCRIPT_SOURCE.source_id, "gdb_transcript")
        self.assertEqual(GDB_TRANSCRIPT_SOURCE.family, "stream")
        self.assertEqual(GDB_TRANSCRIPT_SOURCE.trigger, "passive")
        self.assertFalse(GDB_TRANSCRIPT_SOURCE.requires_halt)
        self.assertTrue(GDB_TRANSCRIPT_SOURCE.supports_parsing)
        self.assertTrue(GDB_TRANSCRIPT_SOURCE.supports_reduction)

        self.assertIsInstance(GDB_HALT_SNAPSHOT_SOURCE, SourceDescriptor)
        self.assertEqual(GDB_HALT_SNAPSHOT_SOURCE.source_id, "gdb_halt_snapshot")
        self.assertEqual(GDB_HALT_SNAPSHOT_SOURCE.family, "snapshot")
        self.assertEqual(GDB_HALT_SNAPSHOT_SOURCE.trigger, "on_halt")
        self.assertTrue(GDB_HALT_SNAPSHOT_SOURCE.requires_halt)
        self.assertTrue(GDB_HALT_SNAPSHOT_SOURCE.supports_parsing)
        self.assertTrue(GDB_HALT_SNAPSHOT_SOURCE.supports_reduction)

    def test_canonical_gdb_transcript_source_module_exports_stream_descriptor(self) -> None:
        self.assertIsInstance(CANONICAL_GDB_TRANSCRIPT_SOURCE, SourceDescriptor)
        self.assertEqual(CANONICAL_GDB_TRANSCRIPT_SOURCE.source_id, "gdb_transcript")
        self.assertEqual(CANONICAL_GDB_TRANSCRIPT_SOURCE.family, "stream")

    def test_canonical_gdb_halt_snapshot_module_exports_snapshot_descriptor_and_builder(self) -> None:
        self.assertIsInstance(CANONICAL_GDB_HALT_SNAPSHOT_SOURCE, SourceDescriptor)
        self.assertEqual(CANONICAL_GDB_HALT_SNAPSHOT_SOURCE.source_id, "gdb_halt_snapshot")
        self.assertEqual(CANONICAL_GDB_HALT_SNAPSHOT_SOURCE.family, "snapshot")

        snapshot = build_halt_snapshot(
            latest_stop={"reason": "breakpoint-hit", "frame": {"addr": "0x08000100", "func": "main"}},
            latest_stack=[],
            latest_registers={"13": "0x20002000", "14": "0x08000081", "15": "0x08000100"},
            variable_evidence=VariableEvidence(
                locals=[
                    VariableEntry(
                        name="system_state",
                        value="READY",
                        bucket="locals",
                        origin="fixture",
                    )
                ]
            ),
        )

        self.assertEqual(snapshot.stop_reason, "breakpoint-hit")
        self.assertEqual(snapshot.pc, "0x08000100")
        self.assertEqual(snapshot.lr, "0x08000081")
        self.assertEqual(snapshot.sp, "0x20002000")
        self.assertEqual(snapshot.variable_evidence.locals[0].name, "system_state")
        self.assertEqual(snapshot.variable_evidence.locals[0].value, "READY")

    def test_canonical_gdb_register_source_module_exports_snapshot_descriptor(self) -> None:
        self.assertIsInstance(CANONICAL_GDB_REGISTERS_SOURCE, SourceDescriptor)
        self.assertEqual(CANONICAL_GDB_REGISTERS_SOURCE.source_id, "gdb_registers")
        self.assertEqual(CANONICAL_GDB_REGISTERS_SOURCE.family, "snapshot")
        self.assertTrue(CANONICAL_GDB_REGISTERS_SOURCE.requires_halt)

        registers = collect_gdb_registers({"15": "0x08000100", "13": "0x20002000"})
        self.assertEqual(registers["15"], "0x08000100")
        self.assertEqual(registers["13"], "0x20002000")

    def test_canonical_gdb_memory_source_module_exports_snapshot_descriptor(self) -> None:
        self.assertIsInstance(CANONICAL_GDB_MEMORY_SOURCE, SourceDescriptor)
        self.assertEqual(CANONICAL_GDB_MEMORY_SOURCE.source_id, "gdb_memory")
        self.assertEqual(CANONICAL_GDB_MEMORY_SOURCE.family, "snapshot")
        self.assertTrue(CANONICAL_GDB_MEMORY_SOURCE.requires_halt)

        memory = collect_gdb_memory_read(address="0x20002000", size=4, data_hex="44 65 62 75")
        self.assertEqual(memory.address, "0x20002000")
        self.assertEqual(memory.size, 4)
        self.assertEqual(memory.data_hex, "44 65 62 75")


if __name__ == "__main__":
    unittest.main()
