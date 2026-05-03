from __future__ import annotations

import pytest

from anvil.config import AnvilSettings


def test_settings_default_to_current_mini_grader_model(monkeypatch) -> None:
    monkeypatch.delenv("ANVIL_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("ANVIL_OFFLINE", raising=False)
    monkeypatch.delenv("ANVIL_AGENT_MODE", raising=False)
    monkeypatch.delenv("ANVIL_REDACT", raising=False)
    monkeypatch.delenv("ANVIL_REDACT_PATTERNS", raising=False)

    settings = AnvilSettings.from_env()

    assert settings.openai_model == "gpt-5.4-mini"
    assert settings.offline is False
    assert settings.agent_mode == "offline"
    assert settings.redact is True
    assert settings.redaction_patterns == []


def test_settings_read_openai_model_and_offline_flag_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANVIL_OPENAI_MODEL", "gpt-5.5")
    monkeypatch.setenv("ANVIL_OFFLINE", "true")
    monkeypatch.setenv("ANVIL_AGENT_MODE", "openai")
    monkeypatch.setenv("ANVIL_REDACT", "false")
    monkeypatch.setenv("ANVIL_REDACT_PATTERNS", "tenant-[0-9]+; vault://[^\\s]+")

    settings = AnvilSettings.from_env()

    assert settings.openai_model == "gpt-5.5"
    assert settings.offline is True
    assert settings.agent_mode == "openai"
    assert settings.redact is False
    assert settings.redaction_patterns == ["tenant-[0-9]+", "vault://[^\\s]+"]


def test_settings_reject_invalid_custom_redaction_regex(monkeypatch) -> None:
    monkeypatch.setenv("ANVIL_REDACT_PATTERNS", "tenant-[")

    with pytest.raises(ValueError, match="ANVIL_REDACT_PATTERNS contains invalid regex"):
        AnvilSettings.from_env()
