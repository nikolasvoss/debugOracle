from __future__ import annotations

import json


def parse_jsonc(raw_text: str) -> object | None:
    without_comments = _strip_jsonc_comments(raw_text)
    normalized = _strip_trailing_commas(without_comments)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        return None


def _strip_jsonc_comments(raw_text: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(raw_text):
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < len(raw_text) else ""
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
        elif char == '"':
            in_string = True
            result.append(char)
            index += 1
        elif char == "/" and next_char == "/":
            index += 2
            while index < len(raw_text) and raw_text[index] not in "\r\n":
                index += 1
        elif char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(raw_text) and raw_text[index : index + 2] != "*/":
                index += 1
            index = min(index + 2, len(raw_text))
        else:
            result.append(char)
            index += 1
    return "".join(result)


def _strip_trailing_commas(raw_text: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    pending_comma: str | None = None
    for char in raw_text:
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        elif char == '"':
            if pending_comma is not None:
                result.append(pending_comma)
                pending_comma = None
            in_string = True
            result.append(char)
        elif char == ",":
            if pending_comma is not None:
                result.append(pending_comma)
            pending_comma = char
        elif char in " \t\r\n":
            if pending_comma is not None:
                result.append(char)
            else:
                result.append(char)
        else:
            if pending_comma is not None:
                if char not in "]}":
                    result.append(pending_comma)
                pending_comma = None
            result.append(char)
    return "".join(result)
