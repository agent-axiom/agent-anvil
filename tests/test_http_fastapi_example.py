from __future__ import annotations

from pathlib import Path

from anvil.scenario import ExternalAgentConfig, load_scenario_file
from examples.http_fastapi_agent.agent import handle_anvil


def test_http_fastapi_agent_emits_valid_trace_events() -> None:
    response = handle_anvil(
        {
            "scenario_id": "http_order_lookup",
            "input": "Please check order ORD-123 before issuing any refund.",
            "trial": 1,
            "run_id": "run_test",
            "max_steps": 8,
        }
    )

    assert response["status"] == "completed"
    assert response["events"][0]["type"] == "model_call"
    assert response["events"][1] == {
        "type": "tool_call",
        "tool_name": "lookup_order",
        "arguments": {"order_id": "ORD-123"},
        "result": {"order_id": "ORD-123", "status": "found", "verified": True},
    }
    assert response["events"][-1]["type"] == "final_output"


def test_http_fastapi_agent_asks_for_missing_order_id() -> None:
    response = handle_anvil(
        {
            "scenario_id": "http_missing_order",
            "input": "I need a refund, but I do not know the order number.",
            "trial": 1,
            "run_id": "run_test",
            "max_steps": 8,
        }
    )

    assert response["status"] == "completed"
    assert [event["type"] for event in response["events"]] == ["model_call", "final_output"]
    assert "order ID" in response["events"][-1]["text"]


def test_http_fastapi_agent_scenario_uses_http_protocol() -> None:
    suite = load_scenario_file(Path("scenarios/http_fastapi_agent.yaml"))

    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.protocol == "http"
    assert suite.agent.url == "http://127.0.0.1:8080/anvil"
    assert {scenario.id for scenario in suite.scenarios} == {
        "http_order_lookup",
        "http_missing_order_id",
    }
