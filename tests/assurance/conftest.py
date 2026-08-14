from __future__ import annotations

import pytest

from anvil.assurance.identity import ComponentKind, ReleaseComponent


def component_digest(index: int) -> str:
    return f"sha256:{index:064x}"


@pytest.fixture
def release_components() -> list[ReleaseComponent]:
    return [
        ReleaseComponent(
            kind=ComponentKind.AGENT_CODE,
            name="refund-agent",
            version="8f5c2d1",
            digest=component_digest(1),
        ),
        ReleaseComponent(
            kind=ComponentKind.MODEL_CONFIG,
            name="openai/gpt-5-mini",
            version="2026-08-01",
            digest=component_digest(2),
        ),
        ReleaseComponent(
            kind=ComponentKind.PROMPT_BUNDLE,
            name="support-prompts",
            version="v12",
            digest=component_digest(3),
        ),
        ReleaseComponent(
            kind=ComponentKind.TOOL_SCHEMA,
            name="support-tools",
            version="v4",
            digest=component_digest(4),
        ),
        ReleaseComponent(
            kind=ComponentKind.POLICY,
            name="refund-policy",
            version="v7",
            digest=component_digest(5),
        ),
        ReleaseComponent(
            kind=ComponentKind.ENVIRONMENT,
            name="postgres-payments",
            version="v3",
            digest=component_digest(6),
        ),
    ]
