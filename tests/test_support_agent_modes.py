from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

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
                ]
            )
        return FakeResponse(
            output=[
                FakeOutputItem(
                    type="message",
                    content=[FakeOutputItem(type="output_text", text="I found the order.")],
                )
            ],
            output_text="I found the order.",
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


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
        model="gpt-test",
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
    assert client.responses.calls[0]["model"] == "gpt-test"
    second_input = client.responses.calls[1]["input"]
    assert isinstance(second_input, list)
    last_input = second_input[-1]
    assert isinstance(last_input, dict)
    last_input_dict = cast(dict[str, Any], last_input)
    assert last_input_dict["type"] == "function_call_output"
