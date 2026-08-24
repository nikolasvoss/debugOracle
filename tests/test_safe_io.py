from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from debugoracle.cli.commands.evidence import emit as emit_evidence_output
from debugoracle.cli.commands.status_capture import emit as emit_status_output
from debugoracle.safe_io import SafeIOError, atomic_write_text, open_stream_output


class SafeIOTests(unittest.TestCase):
    def test_cli_render_outputs_reject_symlink_targets_without_traceback(self) -> None:
        for emitter in (emit_evidence_output, emit_status_output):
            with self.subTest(emitter=emitter.__module__):
                with tempfile.TemporaryDirectory() as tmpdir:
                    sentinel = Path(tmpdir) / "sentinel.txt"
                    sentinel.write_text("sentinel", encoding="utf-8")
                    output = Path(tmpdir) / "output.txt"
                    output.symlink_to(sentinel)
                    stderr = io.StringIO()

                    with redirect_stderr(stderr):
                        code = emitter("replacement", str(output))

                    self.assertEqual(code, 1)
                    self.assertIn("safely write", stderr.getvalue().lower())
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel")

    def test_cli_render_outputs_do_not_create_directories_through_symlink_parent(
        self,
    ) -> None:
        for emitter in (emit_evidence_output, emit_status_output):
            with self.subTest(emitter=emitter.__module__):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    outside = root / "outside"
                    outside.mkdir()
                    (root / "linked").symlink_to(outside, target_is_directory=True)
                    stderr = io.StringIO()

                    with redirect_stderr(stderr):
                        code = emitter(
                            "replacement",
                            str(root / "linked" / "new" / "output.txt"),
                        )

                    self.assertEqual(code, 1)
                    self.assertIn("safely write", stderr.getvalue().lower())
                    self.assertFalse((outside / "new").exists())

    def test_workspace_atomic_write_rejects_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            outside = Path(tmpdir) / "sentinel.txt"
            root.mkdir()
            outside.write_text("sentinel", encoding="utf-8")
            target = root / "snapshot.json"
            target.symlink_to(outside)

            with self.assertRaises(SafeIOError):
                atomic_write_text(target, "replacement", workspace_root=root)

            self.assertEqual(outside.read_text(encoding="utf-8"), "sentinel")

    def test_workspace_atomic_write_rejects_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            outside = Path(tmpdir) / "outside"
            root.mkdir()
            outside.mkdir()
            sentinel = outside / "snapshot.json"
            sentinel.write_text("sentinel", encoding="utf-8")
            (root / "state").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(SafeIOError):
                atomic_write_text(
                    root / "state" / "snapshot.json",
                    "replacement",
                    workspace_root=root,
                )

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel")

    def test_workspace_atomic_write_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir()
            outside = Path(tmpdir) / "outside.json"

            with self.assertRaises(SafeIOError):
                atomic_write_text(outside, "data", workspace_root=root)

            self.assertFalse(outside.exists())

    def test_workspace_atomic_write_rejects_nested_dot_dot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaisesRegex(SafeIOError, "components"):
                atomic_write_text(
                    root / "state" / ".." / "snapshot.json",
                    "data",
                    workspace_root=root,
                )
            self.assertFalse((root / "snapshot.json").exists())

    def test_failed_atomic_replace_preserves_previous_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "state.json"
            target.write_text('{"status": "old"}\n', encoding="utf-8")

            with (
                patch("debugoracle.safe_io.os.replace", side_effect=OSError("ENOSPC")),
                self.assertRaises(SafeIOError),
            ):
                atomic_write_text(
                    target,
                    '{"status": "new"}\n',
                    workspace_root=root,
                )

            self.assertEqual(target.read_text(encoding="utf-8"), '{"status": "old"}\n')
            self.assertEqual(list(root.glob(".state.json.tmp-*")), [])

    def test_atomic_replace_preserves_existing_mode_despite_restrictive_umask(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "state.json"
            target.write_text("old", encoding="utf-8")
            target.chmod(0o640)
            previous_umask = os.umask(0o077)
            try:
                atomic_write_text(target, "new")
            finally:
                os.umask(previous_umask)

            self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_stream_output_preserves_append_and_truncate_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "session.rtt"
            target.write_bytes(b"old")
            with open_stream_output(target, append=True, workspace_root=root) as handle:
                handle.write(b"+new")
            self.assertEqual(target.read_bytes(), b"old+new")

            with open_stream_output(
                target, append=False, workspace_root=root
            ) as handle:
                handle.write(b"replacement")
            self.assertEqual(target.read_bytes(), b"replacement")

    def test_stream_output_rejects_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir()
            sentinel = Path(tmpdir) / "sentinel.log"
            sentinel.write_bytes(b"sentinel")
            target = root / "session.rtt"
            target.symlink_to(sentinel)

            with self.assertRaises(SafeIOError):
                open_stream_output(target, append=False, workspace_root=root)

            self.assertEqual(sentinel.read_bytes(), b"sentinel")

    def test_stream_output_rejects_hard_link_without_truncating_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir()
            sentinel = Path(tmpdir) / "sentinel.log"
            sentinel.write_bytes(b"sentinel")
            target = root / "session.rtt"
            target.hardlink_to(sentinel)

            with self.assertRaisesRegex(SafeIOError, "hard links"):
                open_stream_output(target, append=False, workspace_root=root)

            self.assertEqual(sentinel.read_bytes(), b"sentinel")


if __name__ == "__main__":
    unittest.main()
