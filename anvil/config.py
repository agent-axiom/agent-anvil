from __future__ import annotations

import os

from pydantic import BaseModel

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


class AnvilSettings(BaseModel):
    openai_model: str = DEFAULT_OPENAI_MODEL
    offline: bool = False

    @classmethod
    def from_env(cls) -> AnvilSettings:
        return cls(
            openai_model=os.getenv("ANVIL_OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            offline=_env_bool("ANVIL_OFFLINE"),
        )


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
