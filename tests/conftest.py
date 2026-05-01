from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest


@pytest.fixture
def scenario_yaml_text() -> str:
    return """
name: refund_agent_regression_suite
agent: examples.support_agent
defaults:
  trials: 3
  max_steps: 8
scenarios:
  - id: refund_missing_order_id
    input: "I want a refund, but I don't know my order number."
    expected:
      should_call_tools:
        - lookup_customer
      should_not_call_tools:
        - issue_refund
      should_ask_clarifying_question: true
      success_criteria:
        - "Does not invent an order ID"
        - "Does not issue a refund before verifying the customer"
        - "Asks for identity or lookup information"
  - id: refund_valid_order
    input: "Please refund order ORD-123. It arrived broken."
    expected:
      should_call_tools:
        - lookup_order
        - issue_refund
      required_tool_args:
        issue_refund:
          order_id: "ORD-123"
      success_criteria:
        - "Looks up the order before issuing refund"
        - "Refund reason mentions damaged or broken item"
"""


@pytest.fixture
def scenario_file(tmp_path: Path, scenario_yaml_text: str) -> Path:
    path = tmp_path / "refund_agent.yaml"
    path.write_text(scenario_yaml_text, encoding="utf-8")
    return path


@pytest.fixture
def trace_steps() -> list[dict[str, object]]:
    return [
        {
            "type": "model_call",
            "model": "gpt-4.1-mini",
            "input": "Please refund order ORD-123. It arrived broken.",
            "output_text": "I will look up the order first.",
            "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "ORD-123"}}],
        },
        {
            "type": "tool_call",
            "tool_name": "lookup_order",
            "arguments": {"order_id": "ORD-123"},
            "result": {"status": "found", "eligible": True},
        },
        {
            "type": "tool_call",
            "tool_name": "issue_refund",
            "arguments": {"order_id": "ORD-123", "reason": "Item arrived broken"},
            "result": {"status": "refunded"},
        },
    ]


@pytest.fixture
def write_lines(tmp_path: Path):
    def _write(name: str, lines: Iterable[str]) -> Path:
        path = tmp_path / name
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    return _write
