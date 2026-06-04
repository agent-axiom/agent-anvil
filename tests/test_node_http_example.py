from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from anvil.scenario import ExternalAgentConfig, load_scenario_file

NODE_AGENT = Path("examples/node_http_agent/agent.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_http_agent_cli_emits_valid_trace_events() -> None:
    response = _run_node_agent(
        {
            "scenario_id": "node_order_lookup",
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_http_agent_cli_asks_for_missing_order_id() -> None:
    response = _run_node_agent(
        {
            "scenario_id": "node_missing_order_id",
            "input": "I need a refund, but I do not know the order number.",
            "trial": 1,
            "run_id": "run_test",
            "max_steps": 8,
        }
    )

    assert response["status"] == "completed"
    assert [event["type"] for event in response["events"]] == ["model_call", "final_output"]
    assert "order ID" in response["events"][-1]["text"]


def test_node_http_agent_scenario_uses_http_protocol() -> None:
    suite = load_scenario_file(Path("scenarios/node_http_agent.yaml"))

    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.protocol == "http"
    assert suite.agent.url == "http://127.0.0.1:8081/anvil"
    assert {scenario.id for scenario in suite.scenarios} == {
        "node_order_lookup",
        "node_missing_order_id",
    }


def _run_node_agent(payload: dict[str, object]) -> dict[str, Any]:
    completed = subprocess.run(
        ["node", str(NODE_AGENT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    response = json.loads(completed.stdout)
    assert isinstance(response, dict)
    return response
