from __future__ import annotations

from anvil.config import AnvilSettings


def test_settings_default_to_current_mini_grader_model(monkeypatch) -> None:
    monkeypatch.delenv("ANVIL_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("ANVIL_OFFLINE", raising=False)
    monkeypatch.delenv("ANVIL_AGENT_MODE", raising=False)

    settings = AnvilSettings.from_env()

    assert settings.openai_model == "gpt-5.4-mini"
    assert settings.offline is False
    assert settings.agent_mode == "offline"


def test_settings_read_openai_model_and_offline_flag_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANVIL_OPENAI_MODEL", "gpt-5.5")
    monkeypatch.setenv("ANVIL_OFFLINE", "true")
    monkeypatch.setenv("ANVIL_AGENT_MODE", "openai")

    settings = AnvilSettings.from_env()

    assert settings.openai_model == "gpt-5.5"
    assert settings.offline is True
    assert settings.agent_mode == "openai"
