from __future__ import annotations

from anvil.config import AnvilSettings


def test_settings_read_openai_model_and_offline_flag_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANVIL_OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("ANVIL_OFFLINE", "true")

    settings = AnvilSettings.from_env()

    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.offline is True
