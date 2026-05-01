from __future__ import annotations

import os

from pydantic import BaseModel


class AnvilSettings(BaseModel):
    openai_model: str = "gpt-4.1-mini"
    offline: bool = False

    @classmethod
    def from_env(cls) -> AnvilSettings:
        return cls(
            openai_model=os.getenv("ANVIL_OPENAI_MODEL", "gpt-4.1-mini"),
            offline=_env_bool("ANVIL_OFFLINE"),
        )


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
