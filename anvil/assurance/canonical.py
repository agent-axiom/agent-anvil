from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def validate_finite_json(value: Any) -> Any:
    """Return a JSON value after rejecting non-finite numeric leaves."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise ValueError("value must contain only finite JSON numbers")
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value deterministically as UTF-8."""
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return rendered.encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("value is not canonical JSON") from None


def sha256_bytes(content: bytes, *, prefix: bool = True) -> str:
    """Return a lowercase SHA-256 digest for bytes."""
    digest = hashlib.sha256(content).hexdigest()
    return f"sha256:{digest}" if prefix else digest


def sha256_json(value: Any) -> str:
    """Return a prefixed SHA-256 digest for canonical JSON."""
    return sha256_bytes(canonical_json_bytes(value))
