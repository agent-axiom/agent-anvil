from __future__ import annotations

from typing import Any

import pytest

from anvil.assurance.evidence import evidence_identity
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


@pytest.fixture
def valid_release_contract_payload(
    release_components: list[ReleaseComponent],
) -> dict[str, Any]:
    return {
        "apiVersion": "assurance.anvil.dev/release-contract/v1alpha1",
        "kind": "ReleaseContract",
        "metadata": {
            "name": "refund-agent-postgres",
            "severity": "critical",
            "labels": {"owner": "payments-platform"},
        },
        "release": {
            "components": [component.model_dump(mode="json") for component in release_components]
        },
        "actor": {
            "identity": "refund-agent",
            "permissions": ["orders.read", "payments.refund"],
        },
        "task": {"inputRef": "fixtures/refund-order-42.json"},
        "packs": [{"name": "anvil-pack-postgres", "version": ">=0.1,<0.2"}],
        "checks": [
            {
                "id": "order-refunded-once",
                "type": "postgres.row_count.v1",
                "config": {
                    "table": "public.refunds",
                    "where": {"order_id": 42},
                    "equals": 1,
                },
            }
        ],
        "evidence": {
            "require": [
                {
                    "type": "postgres.state_snapshot.v1",
                    "minimumTrust": "L2",
                    "subject": "postgres://payments/public",
                },
                {"type": "agent.trace.v1", "minimumTrust": "L1"},
            ]
        },
        "reliability": {"trials": 20, "minimumPassRate": 0.95},
    }


@pytest.fixture
def evidence_record_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": "assurance.anvil.dev/evidence-record/v1alpha1",
        "runId": "assure_20260814_001",
        "releaseId": f"sha256:{'7' * 64}",
        "contractId": "refund-agent-postgres",
        "type": "postgres.state_snapshot.v1",
        "trustLevel": "L2",
        "subject": "postgres://payments/public",
        "source": {
            "collector": "postgres-observer",
            "version": "0.1.0",
            "boundary": "separate-read-only-credentials",
        },
        "observedAt": "2026-08-14T12:00:00Z",
        "content": {
            "mediaType": "application/json",
            "sha256": "8" * 64,
            "sizeBytes": 4096,
            "path": f"objects/81/{'8' * 62}",
        },
        "parents": [],
        "correlations": {
            "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
            "transactionId": "735128",
        },
        "redaction": {
            "applied": True,
            "policyDigest": f"sha256:{'9' * 64}",
        },
    }
    payload["evidenceId"] = evidence_identity(payload)
    return payload
