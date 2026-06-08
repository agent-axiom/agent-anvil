from __future__ import annotations

from typing import Any


def is_supported_json_path(path: str) -> bool:
    if path == "$":
        return True
    return _parse_json_path(path) is not None


def json_path_get(value: Any, path: str) -> Any:
    tokens = _parse_json_path(path)
    if tokens is None:
        return None

    selected = value
    for token in tokens:
        if isinstance(token, str):
            if not isinstance(selected, dict):
                return None
            selected = selected.get(token)
            continue
        if not isinstance(selected, list) or token >= len(selected):
            return None
        selected = selected[token]
    return selected


def _parse_json_path(path: str) -> list[str | int] | None:
    if path == "$":
        return []
    if not path.startswith("$"):
        return None

    tokens: list[str | int] = []
    remainder = path[1:]
    while remainder:
        if remainder.startswith("."):
            key, remainder = _consume_json_path_key(remainder[1:])
            if key is None:
                return None
            tokens.append(key)
            continue
        if remainder.startswith("["):
            index, remainder = _consume_json_path_index(remainder)
            if index is None:
                return None
            tokens.append(index)
            continue
        return None
    return tokens


def _consume_json_path_key(remainder: str) -> tuple[str | None, str]:
    if not remainder or remainder[0] in ".[":
        return None, remainder

    key_end = len(remainder)
    for delimiter in (".", "["):
        delimiter_index = remainder.find(delimiter)
        if delimiter_index != -1:
            key_end = min(key_end, delimiter_index)

    key = remainder[:key_end]
    if not all(character.isalnum() or character in {"_", "-"} for character in key):
        return None, remainder[key_end:]
    return key, remainder[key_end:]


def _consume_json_path_index(remainder: str) -> tuple[int | None, str]:
    closing_index = remainder.find("]")
    if closing_index == -1:
        return None, remainder

    index_text = remainder[1:closing_index]
    if not index_text.isdigit():
        return None, remainder[closing_index + 1 :]
    return int(index_text), remainder[closing_index + 1 :]
