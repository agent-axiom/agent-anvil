from __future__ import annotations

import re
from typing import Any

API_KEY_RE = re.compile(r"\b(?:sk|rk|pk|ak|xox[baprs]?)-[A-Za-z0-9_-]{10,}\b")
BEARER_TOKEN_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE)
GENERIC_SECRET_RE = re.compile(
    r"\b(api[_-]?key|secret|token|password)\s*[:=]\s*([\"']?)([A-Za-z0-9._~+/=-]{8,})(\2)",
    re.IGNORECASE,
)
JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ORDER_ID_RE = re.compile(r"\bORD-[A-Za-z0-9-]+\b")
CUSTOMER_ID_RE = re.compile(r"\b(?:CUS-[A-Za-z0-9-]+|cus_[A-Za-z0-9_]+)\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
SECRET_KEY_RE = re.compile(
    r"(?:^|_)(?:api_?key|access_token|refresh_token|id_token|token|password|secret|"
    r"client_secret|private_key)(?:$|_)",
    re.IGNORECASE,
)
API_KEY_NAME_RE = re.compile(r"api_?key", re.IGNORECASE)


def redact_payload(value: Any, *, patterns: list[str] | None = None) -> Any:
    if isinstance(value, dict):
        return {key: _redact_by_key(key, item, patterns=patterns) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item, patterns=patterns) for item in value]
    if isinstance(value, str):
        return redact_text(value, patterns=patterns)
    return value


def _redact_by_key(key: str, value: Any, *, patterns: list[str] | None = None) -> Any:
    if not SECRET_KEY_RE.search(key):
        return redact_payload(value, patterns=patterns)
    if API_KEY_NAME_RE.search(key):
        return "[REDACTED_API_KEY]"
    return "[REDACTED_SECRET]"


def redact_text(value: str, *, patterns: list[str] | None = None) -> str:
    redacted = BEARER_TOKEN_RE.sub("Bearer [REDACTED_BEARER_TOKEN]", value)
    redacted = JWT_RE.sub("[REDACTED_JWT]", redacted)
    redacted = API_KEY_RE.sub("[REDACTED_API_KEY]", redacted)
    redacted = GENERIC_SECRET_RE.sub(
        lambda match: f"{match.group(1)}={match.group(2)}[REDACTED_SECRET]{match.group(4)}",
        redacted,
    )
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = ORDER_ID_RE.sub("[REDACTED_ORDER_ID]", redacted)
    redacted = CUSTOMER_ID_RE.sub("[REDACTED_CUSTOMER_ID]", redacted)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    for pattern in patterns or []:
        redacted = re.sub(pattern, "[REDACTED_CUSTOM]", redacted)
    return redacted
