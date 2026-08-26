from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from debugoracle.installer.platform.windows import (
    WindowsPathRecord,
    load_managed_path_record,
    write_managed_path_record,
)
from debugoracle.installer.platform import windows


class WindowsPathRecordTests(unittest.TestCase):
    def test_record_round_trip_preserves_the_exact_managed_path_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            record_path = Path(tmpdir) / "managed-path.json"
            record = WindowsPathRecord(entry=r"C:\Users\Niko\.local\bin")

            write_managed_path_record(record_path, record)

            self.assertEqual(load_managed_path_record(record_path), record)

    def test_missing_record_does_not_claim_path_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            record_path = Path(tmpdir) / "managed-path.json"

            self.assertIsNone(load_managed_path_record(record_path))

    def test_record_write_failure_preserves_the_previous_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            record_path = Path(tmpdir) / "managed-path.json"
            previous = WindowsPathRecord(entry=r"C:\old")
            write_managed_path_record(record_path, previous)

            with patch(
                "debugoracle.installer.platform.windows.os.replace",
                side_effect=OSError("nope"),
            ):
                with self.assertRaises(OSError):
                    write_managed_path_record(
                        record_path, WindowsPathRecord(entry=r"C:\new")
                    )

            self.assertEqual(load_managed_path_record(record_path), previous)

    def test_failed_registry_update_does_not_leave_path_ownership_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            record_path = Path(tmpdir) / "managed-path.json"
            with (
                patch.object(windows, "_read_user_path", return_value=""),
                patch.object(windows, "_write_user_path", side_effect=OSError("nope")),
            ):
                applied, error = windows.append_path_line(record_path, r"C:\bin")

            self.assertFalse(applied)
            self.assertIn("nope", error or "")
            self.assertIsNone(load_managed_path_record(record_path))

    def test_missing_user_path_value_is_treated_as_empty(self) -> None:
        registry = MagicMock()
        registry.OpenKey.return_value.__enter__.return_value = object()
        registry.QueryValueEx.side_effect = FileNotFoundError()
        with patch.object(windows, "_load_winreg", return_value=registry):
            self.assertEqual(windows._read_user_path(), "")

    def test_path_change_before_install_write_fails_without_claiming_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            record_path = Path(tmpdir) / "managed-path.json"
            with (
                patch.object(windows, "_read_user_path", side_effect=["", r"C:\Other"]),
                patch.object(windows, "_write_user_path") as write_path,
            ):
                applied, error = windows.append_path_line(record_path, r"C:\bin")

            self.assertFalse(applied)
            self.assertIn("changed", error or "")
            write_path.assert_not_called()
            self.assertIsNone(load_managed_path_record(record_path))


if __name__ == "__main__":
    unittest.main()
