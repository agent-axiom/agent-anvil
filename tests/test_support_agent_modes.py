from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from anvil.trace import TraceRun
from examples.support_agent import run_agent
from examples.support_agent.openai_agent import run_agent as run_openai_agent


@dataclass
class FakeOutputItem:
    type: str
    name: str | None = None
    arguments: str | None = None
    call_id: str | None = None
    content: list[object] | None = None
    text: str | None = None


@dataclass
class FakeResponse:
    output: list[FakeOutputItem]
    output_text: str = ""
    usage: dict[str, int] | None = None


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return FakeResponse(
                output=[
                    FakeOutputItem(
                        type="function_call",
                        name="lookup_order",
                        arguments='{"order_id": "ORD-123"}',
                        call_id="call_lookup",
                    )
                ],
                usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            )
        return FakeResponse(
            output=[
                FakeOutputItem(
                    type="message",
                    content=[FakeOutputItem(type="output_text", text="I found the order.")],
                )
            ],
            output_text="I found the order.",
            usage={"input_tokens": 80, "output_tokens": 25, "total_tokens": 105},
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


class FakeMalformedToolArgsResponses:
    def create(self, **__: object) -> FakeResponse:
        return FakeResponse(
            output=[
                FakeOutputItem(
                    type="function_call",
                    name="lookup_order",
                    arguments="{not-json",
                    call_id="call_bad_args",
                )
            ]
        )


class FakeMalformedToolArgsClient:
    def __init__(self) -> None:
        self.responses = FakeMalformedToolArgsResponses()


class FakeToolExecutionErrorResponses:
    def create(self, **__: object) -> FakeResponse:
        return FakeResponse(
            output=[
                FakeOutputItem(
                    type="function_call",
                    name="issue_refund",
                    arguments='{"order_id": "ORD-123"}',
                    call_id="call_missing_reason",
                )
            ]
        )


class FakeToolExecutionErrorClient:
    def __init__(self) -> None:
        self.responses = FakeToolExecutionErrorResponses()


def test_support_agent_offline_mode_keeps_intentional_regression() -> None:
    trace = run_agent(
        input_text="I want a refund, but I don't know my order number.",
        scenario_id="refund_missing_order_id",
        trial=1,
        run_id="run_test",
        max_steps=8,
        agent_mode="offline",
    )

    assert isinstance(trace, TraceRun)
    assert trace.tool_names() == ["lookup_customer", "issue_refund"]
    assert trace.steps[0]["model"] == "offline-demo-agent"
    assert trace.final_output == "I issued the refund even though the order id was missing."


def test_openai_support_agent_executes_responses_tool_calls() -> None:
    client = FakeOpenAIClient()

    trace = run_openai_agent(
        input_text="Please refund order ORD-123. It arrived broken.",
        scenario_id="refund_valid_order",
        trial=1,
        run_id="run_test",
        max_steps=8,
        client=client,
        model="gpt-5.4-mini",
    )

    assert trace.status == "completed"
    assert trace.tool_names() == ["lookup_order"]
    assert trace.steps[0]["type"] == "model_call"
    assert trace.steps[0]["tool_calls"] == [
        {"name": "lookup_order", "arguments": {"order_id": "ORD-123"}}
    ]
    assert trace.steps[1]["result"] == {
        "status": "found",
        "order_id": "ORD-123",
        "customer_id": "cus_123",
        "eligible_for_refund": True,
    }
    assert trace.final_output == "I found the order."
    assert trace.metrics.input_tokens == 180
    assert trace.metrics.output_tokens == 45
    assert trace.metrics.total_tokens == 225
    assert trace.metrics.estimated_cost_usd == pytest.approx(0.0003375)
    assert client.responses.calls[0]["model"] == "gpt-5.4-mini"
    second_input = client.responses.calls[1]["input"]
    assert isinstance(second_input, list)
    assert isinstance(second_input[-2], FakeOutputItem)
    assert second_input[-2].type == "function_call"
    function_output = second_input[-1]
    assert isinstance(function_output, dict)
    function_output_dict = cast(dict[str, Any], function_output)
    assert function_output_dict["type"] == "function_call_output"


def test_openai_support_agent_records_tool_argument_errors() -> None:
    trace = run_openai_agent(
        input_text="Please refund order ORD-123.",
        scenario_id="refund_valid_order",
        trial=1,
        run_id="run_test",
        max_steps=8,
        client=FakeMalformedToolArgsClient(),
        model="gpt-5.4-mini",
    )

    assert trace.status == "failed"
    assert trace.steps[0]["type"] == "model_call"
    assert trace.steps[1]["type"] == "tool_argument_error"
    assert trace.steps[1]["tool_name"] == "lookup_order"
    assert "Invalid JSON tool arguments" in str(trace.final_output)


def test_openai_support_agent_records_tool_execution_errors() -> None:
    trace = run_openai_agent(
        input_text="Please refund order ORD-123.",
        scenario_id="refund_valid_order",
        trial=1,
        run_id="run_test",
        max_steps=8,
        client=FakeToolExecutionErrorClient(),
        model="gpt-5.4-mini",
    )

    assert trace.status == "failed"
    assert trace.steps[0]["type"] == "model_call"
    assert trace.steps[1]["type"] == "tool_execution_error"
    assert trace.steps[1]["tool_name"] == "issue_refund"
    assert "Tool execution failed" in str(trace.final_output)
