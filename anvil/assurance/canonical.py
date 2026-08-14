from __future__ import annotations

import hashlib
import json
from typing import Any


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
    except (TypeError, ValueError) as error:
        raise ValueError(f"value is not canonical JSON: {error}") from error
    return rendered.encode("utf-8")


def sha256_bytes(content: bytes, *, prefix: bool = True) -> str:
    """Return a lowercase SHA-256 digest for bytes."""
    digest = hashlib.sha256(content).hexdigest()
    return f"sha256:{digest}" if prefix else digest


def sha256_json(value: Any) -> str:
    """Return a prefixed SHA-256 digest for canonical JSON."""
    return sha256_bytes(canonical_json_bytes(value))
