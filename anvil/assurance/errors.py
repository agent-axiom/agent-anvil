from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SECRET_DETAIL_KEYS = frozenset({"api_key", "authorization", "password", "secret", "token"})


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
        if SECRET_DETAIL_KEYS.intersection(key.casefold() for key in selected_details):
            raise ValueError("details must not contain secret-like keys")
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = selected_details

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {super().__str__()}"
