from __future__ import annotations

import os

from pydantic import BaseModel

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_AGENT_MODE = "offline"


class AnvilSettings(BaseModel):
    openai_model: str = DEFAULT_OPENAI_MODEL
    offline: bool = False
    agent_mode: str = DEFAULT_AGENT_MODE

    @classmethod
    def from_env(cls) -> AnvilSettings:
        return cls(
            openai_model=os.getenv("ANVIL_OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            offline=_env_bool("ANVIL_OFFLINE"),
            agent_mode=os.getenv("ANVIL_AGENT_MODE", DEFAULT_AGENT_MODE),
        )


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
