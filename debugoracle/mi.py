from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn


class MIParseError(ValueError):
    """Raised when the GDB/MI transcript cannot be parsed."""


@dataclass
class MIRecord:
    prefix: str
    kind: str
    data: dict[str, object]
    raw: str


def parse_mi_record(line: str) -> MIRecord | None:
    line = line.strip()
    if not line:
        return None

    cursor = 0
    while cursor < len(line) and line[cursor].isdigit():
        cursor += 1
    if cursor:
        line = line[cursor:].lstrip()
        if not line:
            return None

    if line[0] not in {"^", "*", "=", "+"}:
        return None

    prefix = line[0]
    body = line[1:]
    if "," in body:
        kind, payload = body.split(",", 1)
        data = _ValueParser(payload).parse_payload()
    else:
        kind = body
        data = {}
    return MIRecord(prefix=prefix, kind=kind, data=data, raw=line)


class _ValueParser:
    MAX_NESTING = 128

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.depth = 0

    def parse_results(self) -> dict[str, object]:
        results: dict[str, object] = {}
        while not self._eof():
            self._skip_ws()
            if self._eof():
                break
            self._reject_unexpected_closer()
            key = self._parse_identifier()
            self._expect("=")
            value = self._parse_value()
            if key in results:
                existing = results[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    results[key] = [existing, value]
            else:
                results[key] = value
            self._skip_ws()
            if self._eof():
                break
            self._expect(",")
            self._skip_ws()
            if self._eof():
                self._error("Trailing comma")
        return results

    def parse_payload(self) -> dict[str, object]:
        self._skip_ws()
        if self._eof():
            return {}
        result: dict[str, object]
        if self._peek() == "{":
            result = self._parse_tuple()
        elif self._peek() == "[":
            result = {"result": self._parse_list()}
        else:
            result = self.parse_results()
        self._skip_ws()
        if not self._eof():
            self._error("Unexpected trailing input")
        return result

    def _parse_value(self) -> object:
        self._skip_ws()
        if self._eof():
            self._error("Expected value")
        char = self._peek()
        if char in {",", "]", "}"}:
            self._error(f"Unexpected closing delimiter {char!r}")
        if char == '"':
            return self._parse_string()
        if char == "{":
            return self._parse_tuple()
        if char == "[":
            return self._parse_list()
        return self._parse_bareword()

    def _parse_tuple(self) -> dict[str, object]:
        self._expect("{")
        self._enter_collection()
        try:
            self._skip_ws()
            if self._consume_if("}"):
                return {}
            values: dict[str, object] = {}
            while True:
                self._reject_unexpected_closer(expected="}")
                key = self._parse_identifier()
                self._expect("=")
                value = self._parse_value()
                if key in values:
                    existing = values[key]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        values[key] = [existing, value]
                else:
                    values[key] = value
                self._skip_ws()
                if self._consume_if("}"):
                    return values
                self._expect(",")
                self._skip_ws()
                if self._consume_if("}"):
                    self._error("Trailing comma")
        finally:
            self.depth -= 1

    def _parse_list(self) -> list[object]:
        self._expect("[")
        self._enter_collection()
        try:
            self._skip_ws()
            if self._consume_if("]"):
                return []
            items: list[object] = []
            while True:
                if self._eof():
                    self._error("Unterminated list")
                self._reject_unexpected_closer(expected="]")
                if self._looks_like_result():
                    key = self._parse_identifier()
                    self._expect("=")
                    items.append({key: self._parse_value()})
                else:
                    items.append(self._parse_value())
                self._skip_ws()
                if self._consume_if("]"):
                    return items
                self._expect(",")
                self._skip_ws()
                if self._consume_if("]"):
                    self._error("Trailing comma")
        finally:
            self.depth -= 1

    def _looks_like_result(self) -> bool:
        if self._eof():
            return False
        char = self._peek()
        if not (char.isalpha() or char in {"_", "-"}):
            return False
        cursor = self.pos
        while cursor < len(self.text):
            current = self.text[cursor]
            if current == "=":
                return True
            if current in {",", "]", "}", '"'}:
                return False
            cursor += 1
        return False

    def _parse_identifier(self) -> str:
        start = self.pos
        self._skip_ws()
        start = self.pos
        while not self._eof():
            char = self._peek()
            if char.isalnum() or char in {"_", "-", "."}:
                self.pos += 1
                continue
            break
        if start == self.pos:
            raise MIParseError(
                f"Expected identifier at position {self.pos}: {self.text!r}"
            )
        return self.text[start : self.pos]

    def _parse_string(self) -> str:
        self._expect('"')
        chars: list[str] = []
        while not self._eof():
            char = self._peek()
            self.pos += 1
            if char == '"':
                return "".join(chars)
            if char == "\\":
                if self._eof():
                    break
                escaped = self._peek()
                self.pos += 1
                mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                chars.append(mapping.get(escaped, escaped))
                continue
            chars.append(char)
        self._error("Unterminated string")

    def _parse_bareword(self) -> str:
        start = self.pos
        while not self._eof() and self._peek() not in {",", "]", "}", " ", "\t"}:
            self.pos += 1
        if start == self.pos:
            self._error("Expected value")
        return self.text[start : self.pos]

    def _expect(self, token: str) -> None:
        if not self._consume_if(token):
            raise MIParseError(
                f"Expected {token!r} at position {self.pos}: {self.text!r}"
            )

    def _consume_if(self, token: str) -> bool:
        if self.text.startswith(token, self.pos):
            self.pos += len(token)
            return True
        return False

    def _peek(self) -> str:
        if self._eof():
            self._error("Unexpected end of input")
        return self.text[self.pos]

    def _skip_ws(self) -> None:
        while not self._eof() and self.text[self.pos].isspace():
            self.pos += 1

    def _eof(self) -> bool:
        return self.pos >= len(self.text)

    def _reject_unexpected_closer(self, *, expected: str | None = None) -> None:
        if self._eof():
            return
        char = self._peek()
        if char in {"]", "}"} and char != expected:
            self._error(f"Unexpected closing delimiter {char!r}")

    def _enter_collection(self) -> None:
        self.depth += 1
        if self.depth > self.MAX_NESTING:
            self._error(f"Nesting exceeds limit {self.MAX_NESTING}")

    def _error(self, message: str) -> NoReturn:
        raise MIParseError(f"{message} at position {self.pos}: {self.text!r}")
