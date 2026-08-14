from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SECRET_DETAIL_KEYS = frozenset(
    {
        "apikey",
        "xapikey",
        "authorization",
        "password",
        "passwd",
        "secret",
        "clientsecret",
        "token",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "bearertoken",
        "jwt",
        "privatekey",
        "signingkey",
        "credential",
        "credentials",
    }
)


def is_secret_like_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in SECRET_DETAIL_KEYS


def contains_secret_like_key(value: object) -> bool:
    pending = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            for key, nested in current.items():
                if is_secret_like_key(key):
                    return True
                pending.append(nested)
        elif isinstance(current, (list, tuple, set, frozenset)):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            pending.extend(current)
    return False


class AssuranceError(ValueError):
    """Expected Assurance failure with a stable code and field path."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        path: str = "$",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        selected_details = dict(details or {})
        if contains_secret_like_key(selected_details):
            raise ValueError("details must not contain secret-like keys")
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = selected_details

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {super().__str__()}"
