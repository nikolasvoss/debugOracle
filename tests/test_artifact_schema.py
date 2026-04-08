from __future__ import annotations

import json
import os
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from debugoracle.artifacts.models import (
    CURRENT_BUNDLE_SCHEMA_VERSION,
    InvestigationArtifact,
    VariableEntry,
)
from debugoracle.artifacts.repository import (
    ArtifactLoadError,
    load_artifact,
    save_artifact,
)
from debugoracle.builder import build_bundle_from_text


FIXTURES = Path(__file__).parent / "fixtures"


class ArtifactSchemaTests(unittest.TestCase):
    def test_canonical_artifact_api_supports_round_trip_without_legacy_bundle_names(
        self,
    ) -> None:
        artifact = build_bundle_from_text("", "")
        artifact.live_state = {"source": "canonical-artifact"}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.json"
            save_artifact(artifact, str(path))
            loaded = load_artifact(str(path))

        self.assertIs(InvestigationArtifact, type(artifact))
        self.assertIsInstance(loaded, InvestigationArtifact)
        self.assertEqual(loaded.live_state["source"], "canonical-artifact")

    def test_legacy_bundle_compatibility_surface_is_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            __import__("debugoracle.artifacts.bundle")

        import debugoracle.builder as builder

        self.assertFalse(hasattr(builder, "load_bundle"))
        self.assertFalse(hasattr(builder, "save_bundle"))
        self.assertFalse(hasattr(builder, "SnapshotLoadError"))

    def test_save_bundle_writes_schema_version_and_live_state(self) -> None:
        bundle = build_bundle_from_text("", "")
        bundle.live_state = {
            "backend": "demo",
            "warnings": ["Synthetic data only."],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_artifact(bundle, str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(payload["live_state"]["backend"], "demo")

    def test_save_and_load_preserve_structured_variable_evidence(self) -> None:
        bundle = build_bundle_from_text("", "")
        bundle.variable_evidence.locals.append(
            VariableEntry(
                name="system_state",
                value="READY",
                bucket="locals",
                origin="fixture",
                order=0,
            )
        )
        bundle.variable_evidence.unknown.append(
            VariableEntry(
                name="dup",
                value="shadow",
                bucket="unknown",
                origin="fixture",
                order=1,
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_artifact(bundle, str(path))
            loaded = load_artifact(str(path))

        self.assertEqual(loaded.schema_version, CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertEqual(loaded.variable_evidence.locals[0].name, "system_state")
        self.assertEqual(loaded.variable_evidence.locals[0].value, "READY")
        self.assertEqual(loaded.variable_evidence.unknown[0].name, "dup")

    def test_builder_defaults_to_catalog_only_register_embedding(self) -> None:
        bundle = build_bundle_from_text(
            '*stopped,reason="breakpoint-hit"\n^done\n',
            "line one\n",
            svd_file_path=str(FIXTURES / "sample.svd"),
        )

        self.assertTrue(bundle.has_embedded_register_source)
        self.assertEqual(bundle.sources.registers.success_count, 0)
        self.assertEqual(bundle.sources.registers.failure_count, 0)
        self.assertEqual(bundle.provenance["register_capture_mode"], "catalog")

    def test_save_and_load_round_trip_embeds_register_sources_object(self) -> None:
        try:
            with _FakeOpenOcdServer(
                values={0x48000000: "0xaaaaaaaa", 0x48000010: "0x00000001"}
            ) as server:
                with patch.dict(
                    os.environ,
                    {
                        "DEBUGORACLE_OPENOCD_HOST": server.host,
                        "DEBUGORACLE_OPENOCD_PORT": str(server.port),
                    },
                    clear=False,
                ):
                    bundle = build_bundle_from_text(
                        '*stopped,reason="breakpoint-hit"\n^done\n',
                        "line one\n",
                        svd_file_path=str(FIXTURES / "sample.svd"),
                        enable_live_peripheral_capture=True,
                    )
        except PermissionError:
            self.skipTest("sandbox blocks loopback socket creation")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_artifact(bundle, str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_artifact(str(path))

        self.assertIn("registers", payload["sources"])
        self.assertEqual(
            payload["sources"]["registers"]["device_name"], "STM32L432KCTest"
        )
        self.assertEqual(payload["sources"]["registers"]["register_count"], 4)
        self.assertEqual(payload["sources"]["registers"]["success_count"], 2)
        self.assertEqual(payload["sources"]["registers"]["skipped_count"], 2)
        self.assertEqual(payload["provenance"]["register_capture_mode"], "live")
        self.assertTrue(loaded.has_embedded_register_source)
        self.assertEqual(loaded.sources.registers.peripherals[0].name, "GPIOA")

    def test_save_and_load_round_trip_embeds_sources_object(self) -> None:
        bundle = build_bundle_from_text("^done\n", "line one\nline two\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_artifact(bundle, str(path))
            payload = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_artifact(str(path))

        self.assertEqual(payload["schema_version"], CURRENT_BUNDLE_SCHEMA_VERSION)
        self.assertIn("sources", payload)
        self.assertEqual(payload["sources"]["gdb"]["raw_text"], "^done\n")
        self.assertEqual(
            payload["sources"]["gdb"]["event_count"],
            len(payload["sources"]["gdb"]["events"]),
        )
        self.assertEqual(payload["sources"]["rtt"]["raw_text"], "line one\nline two\n")
        self.assertEqual(payload["sources"]["rtt"]["lines"], ["line one", "line two"])
        self.assertEqual(payload["sources"]["rtt"]["line_count"], 2)
        self.assertIn("memory", payload["sources"])
        self.assertEqual(payload["sources"]["memory"]["embedded"], False)
        self.assertEqual(payload["sources"]["memory"]["entries"], [])
        self.assertEqual(loaded.sources.gdb.raw_text, "^done\n")
        self.assertEqual(loaded.sources.rtt.lines, ["line one", "line two"])

    def test_load_artifact_missing_schema_version_fails(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("schema_version", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArtifactLoadError):
                load_artifact(str(path))

    def test_load_artifact_missing_sources_object_fails(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload.pop("sources", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArtifactLoadError):
                load_artifact(str(path))

    def test_load_artifact_missing_sources_memory_object_fails(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload["sources"].pop("memory", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArtifactLoadError):
                load_artifact(str(path))

    def test_load_artifact_unknown_schema_version_fails(self) -> None:
        bundle = build_bundle_from_text("", "")
        payload = bundle.to_dict()
        payload["schema_version"] = "99"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "future.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArtifactLoadError):
                load_artifact(str(path))

    def test_round_trip_preserves_provenance_and_minimal_live_state(self) -> None:
        bundle = build_bundle_from_text("", "")
        bundle.provenance["custom_note"] = {"source": "fixture", "confidence": 1}
        bundle.live_state = {
            "captured_at": "2026-03-18T10:00:00+00:00",
            "source": "demo",
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            save_artifact(bundle, str(path))
            loaded = load_artifact(str(path))

        self.assertEqual(loaded.live_state["source"], "demo")
        self.assertEqual(loaded.provenance["custom_note"]["source"], "fixture")


class _FakeOpenOcdHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        buffer = b""
        while True:
            chunk = self.request.recv(1024)
            if not chunk:
                return
            buffer += chunk
            while b"\x1a" in buffer:
                raw_command, buffer = buffer.split(b"\x1a", 1)
                command = raw_command.decode("utf-8", errors="replace").strip()
                response = self.server.build_response(command)
                self.request.sendall(response.encode("utf-8") + b"\x1a")


class _VirtualOpenOcdSocket:
    def __init__(self, server: "_FakeOpenOcdServer") -> None:
        self._server = server
        self._buffer = bytearray()
        self._closed = False

    def settimeout(self, _: float) -> None:
        return

    def sendall(self, payload: bytes) -> None:
        if self._closed:
            raise OSError("socket is closed")
        chunks = payload.split(b"\x1a")
        for raw_command in chunks:
            if not raw_command:
                continue
            command = raw_command.decode("utf-8", errors="replace").strip()
            response = self._server.build_response(command)
            self._buffer.extend(response.encode("utf-8") + b"\x1a")

    def recv(self, size: int) -> bytes:
        if self._closed:
            return b""
        if not self._buffer:
            return b""
        take = min(size, len(self._buffer))
        chunk = bytes(self._buffer[:take])
        del self._buffer[:take]
        return chunk

    def close(self) -> None:
        self._closed = True


class _FakeOpenOcdServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, *, values: dict[int, str]) -> None:
        self._values = values
        self._init_error: PermissionError | None = None
        self._virtual_mode = False
        self._create_connection_patcher = None
        try:
            super().__init__(("127.0.0.1", 0), _FakeOpenOcdHandler)
        except PermissionError as error:
            self._init_error = error
            self._virtual_mode = True
            self._thread = None
            self.server_address = ("127.0.0.1", 65535)
            return
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        return str(self.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def __enter__(self) -> "_FakeOpenOcdServer":
        if self._virtual_mode:
            self._create_connection_patcher = patch(
                "socket.create_connection",
                side_effect=self._create_virtual_connection,
            )
            self._create_connection_patcher.start()
            return self
        assert self._thread is not None
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._virtual_mode:
            if self._create_connection_patcher is not None:
                self._create_connection_patcher.stop()
            return
        assert self._thread is not None
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=1)

    def build_response(self, command: str) -> str:
        parts = command.split()
        if len(parts) != 4 or parts[0] != "read_memory":
            return "unsupported-command"
        address = int(parts[1], 0)
        count = int(parts[3], 0)
        if count != 1 or address not in self._values:
            return "error"
        return self._values[address]

    def _create_virtual_connection(self, *args, **_kwargs) -> _VirtualOpenOcdSocket:
        endpoint = args[0] if args else None
        if not isinstance(endpoint, tuple) or len(endpoint) < 2:
            raise OSError("Connection refused")
        host = str(endpoint[0])
        port = int(endpoint[1])
        allowed_hosts = {self.host, "127.0.0.1", "localhost"}
        if host not in allowed_hosts or port != self.port:
            raise OSError("Connection refused")
        return _VirtualOpenOcdSocket(self)


if __name__ == "__main__":
    unittest.main()
