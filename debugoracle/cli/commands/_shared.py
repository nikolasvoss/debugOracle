from __future__ import annotations

import json
from pathlib import Path


def resolve_workspace_path(value: str | None, workspace_root: Path) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(workspace_root / path)


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
    length = len(raw_text)
    while index < length:
        char = raw_text[index]
        next_char = raw_text[index + 1] if index + 1 < length else ""
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index += 2
            while index < length and raw_text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < length and not (
                raw_text[index] == "*" and raw_text[index + 1] == "/"
            ):
                index += 1
            index = min(index + 2, length)
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _strip_trailing_commas(raw_text: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    index = 0
    length = len(raw_text)
    while index < length:
        char = raw_text[index]
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < length and raw_text[lookahead] in " \t\r\n":
                lookahead += 1
            if lookahead < length and raw_text[lookahead] in "]}":
                index += 1
                continue
        result.append(char)
        index += 1
    return "".join(result)
