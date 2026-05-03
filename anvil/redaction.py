from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ORDER_ID_RE = re.compile(r"\bORD-[A-Za-z0-9-]+\b")
CUSTOMER_ID_RE = re.compile(r"\b(?:CUS-[A-Za-z0-9-]+|cus_[A-Za-z0-9_]+)\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    redacted = ORDER_ID_RE.sub("[REDACTED_ORDER_ID]", redacted)
    redacted = CUSTOMER_ID_RE.sub("[REDACTED_CUSTOMER_ID]", redacted)
    return PHONE_RE.sub("[REDACTED_PHONE]", redacted)
