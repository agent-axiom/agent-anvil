from __future__ import annotations

import os

from pydantic import BaseModel

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_AGENT_MODE = "offline"


class AnvilSettings(BaseModel):
    openai_model: str = DEFAULT_OPENAI_MODEL
    offline: bool = False
    agent_mode: str = DEFAULT_AGENT_MODE
    redact: bool = True

    @classmethod
    def from_env(cls) -> AnvilSettings:
        return cls(
            openai_model=os.getenv("ANVIL_OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            offline=_env_bool("ANVIL_OFFLINE"),
            agent_mode=os.getenv("ANVIL_AGENT_MODE", DEFAULT_AGENT_MODE),
            redact=_env_bool("ANVIL_REDACT", default=True),
        )


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}
