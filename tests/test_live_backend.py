from __future__ import annotations

import unittest

from debugoracle.live import (
    MAX_MEMORY_READ_BYTES,
    DemoLiveDebugBackend,
    build_live_backend,
    validate_memory_request,
)


class LiveBackendTests(unittest.TestCase):
    def test_build_live_backend_defaults_to_demo(self) -> None:
        backend = build_live_backend()
        self.assertIsInstance(backend, DemoLiveDebugBackend)

    def test_demo_backend_status_reports_available(self) -> None:
        status = DemoLiveDebugBackend().get_status()
        self.assertTrue(status.available)
        self.assertTrue(status.connected)
        self.assertEqual(status.target_state, "stopped")
        self.assertIn("synthetic verification data", status.warnings[0].lower())

    def test_demo_backend_register_read_returns_expected_values(self) -> None:
        result = DemoLiveDebugBackend().read_registers()
        self.assertTrue(result.available)
        self.assertEqual(result.registers["pc"], "0x08000100")
        self.assertEqual(result.registers["sp"], "0x20002000")

    def test_demo_backend_memory_read_returns_bounded_payload(self) -> None:
        result = DemoLiveDebugBackend().read_memory(0x20002000, 8)
        self.assertTrue(result.available)
        self.assertEqual(result.address, "0x20002000")
        self.assertEqual(result.size, 8)
        self.assertEqual(result.ascii_preview, "DebugOra")

    def test_validate_memory_request_rejects_invalid_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid memory address"):
            validate_memory_request("not-an-address", 8)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            validate_memory_request("0x20002000", 0)
        with self.assertRaisesRegex(ValueError, "safe limit"):
            validate_memory_request("0x20002000", MAX_MEMORY_READ_BYTES + 1)

    def test_demo_backend_maps_unavailable_state_consistently(self) -> None:
        backend = DemoLiveDebugBackend(available=False)
        status = backend.get_status()
        registers = backend.read_registers()
        memory = backend.read_memory(0x20002000, 4)

        self.assertFalse(status.available)
        self.assertFalse(registers.available)
        self.assertFalse(memory.available)
        self.assertIn("disabled", "\n".join(registers.warnings).lower())
        self.assertIn("disabled", "\n".join(memory.warnings).lower())


if __name__ == "__main__":
    unittest.main()
