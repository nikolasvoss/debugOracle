from __future__ import annotations

import unittest

from debugoracle.mi import MIParseError, parse_mi_record


class MIParseTests(unittest.TestCase):
    def test_mismatched_list_closer_raises_instead_of_hanging(self) -> None:
        with self.assertRaisesRegex(MIParseError, "position"):
            parse_mi_record("^done,result=[}]")

    def test_malformed_collections_fail_with_a_position(self) -> None:
        malformed = [
            "^done,result={]",
            "^done,result=",
            "^done,result=[,]",
            "^done,result=[value,]",
            "^done,result={value=one,}",
            "^done,result=[{value=one]}",
            "^done,result=[value",
            '^done,result="unterminated',
            '^done,result="escape\\',
        ]
        for record in malformed:
            with (
                self.subTest(record=record),
                self.assertRaisesRegex(MIParseError, "position"),
            ):
                parse_mi_record(record)

    def test_excessive_nesting_fails_closed(self) -> None:
        record = "^done,result=" + "[" * 129 + "value" + "]" * 129
        with self.assertRaisesRegex(MIParseError, "Nesting exceeds limit"):
            parse_mi_record(record)

    def test_parse_mi_record_accepts_token_prefix(self) -> None:
        record = parse_mi_record('15^done,foo="bar"')
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.prefix, "^")
        self.assertEqual(record.kind, "done")
        self.assertEqual(record.data.get("foo"), "bar")

    def test_parse_mi_record_accepts_tuple_payload_for_plus_event(self) -> None:
        record = parse_mi_record(
            '17+download,{section=".text",section-size="1234",total-size="2000"}'
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.prefix, "+")
        self.assertEqual(record.kind, "download")
        self.assertEqual(record.data.get("section"), ".text")
        self.assertEqual(record.data.get("section-size"), "1234")
        self.assertEqual(record.data.get("total-size"), "2000")

    def test_parse_mi_record_accepts_plus_prefix(self) -> None:
        record = parse_mi_record('17+download,section=".text"')
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.prefix, "+")
        self.assertEqual(record.kind, "download")
        self.assertEqual(record.data.get("section"), ".text")

    def test_parse_mi_record_preserves_composite_variable_values_as_strings(
        self,
    ) -> None:
        record = parse_mi_record(
            "^done,locals=["
            '{name="arr",value="{1, 2, 3, 4}"},'
            '{name="point",value="{x = 1, y = 2}"},'
            '{name="matrix",value="{{1, 2}, {3, 4}}"},'
            '{name="message",value="[72, 101, 108, 108, 111]"}'
            "]"
        )
        self.assertIsNotNone(record)
        assert record is not None

        locals_payload = record.data.get("locals")
        self.assertIsInstance(locals_payload, list)
        assert isinstance(locals_payload, list)

        self.assertEqual(locals_payload[0]["value"], "{1, 2, 3, 4}")
        self.assertEqual(locals_payload[1]["value"], "{x = 1, y = 2}")
        self.assertEqual(locals_payload[2]["value"], "{{1, 2}, {3, 4}}")
        self.assertEqual(locals_payload[3]["value"], "[72, 101, 108, 108, 111]")


if __name__ == "__main__":
    unittest.main()
