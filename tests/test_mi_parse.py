from __future__ import annotations

import unittest

from debugoracle.mi import parse_mi_record


class MIParseTests(unittest.TestCase):
    def test_parse_mi_record_accepts_token_prefix(self) -> None:
        record = parse_mi_record('15^done,foo="bar"')
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.prefix, "^")
        self.assertEqual(record.kind, "done")
        self.assertEqual(record.data.get("foo"), "bar")

    def test_parse_mi_record_accepts_plus_prefix(self) -> None:
        record = parse_mi_record('17+download,section=".text"')
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.prefix, "+")
        self.assertEqual(record.kind, "download")
        self.assertEqual(record.data.get("section"), ".text")


if __name__ == "__main__":
    unittest.main()
