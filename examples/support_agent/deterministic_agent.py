from __future__ import annotations

from datetime import UTC, datetime

from anvil.trace import TraceRun
from examples.support_agent.tools import issue_refund, lookup_customer, lookup_order

OFFLINE_MODEL_NAME = "offline-demo-agent"


def run_agent(
    *,
    input_text: str,
    scenario_id: str,
    trial: int,
    run_id: str,
    max_steps: int,
) -> TraceRun:
    started_at = datetime.now(UTC)
    steps: list[dict[str, object]] = []

    if "ORD-123" in input_text:
        final_output = _run_valid_refund(input_text, steps)
    else:
        final_output = _run_missing_order_id_regression(input_text, steps)

    status = "failed" if len(steps) > max_steps else "completed"

    return TraceRun(
        run_id=run_id,
        scenario_id=scenario_id,
        trial=trial,
        input=input_text,
        started_at=started_at,
        ended_at=datetime.now(UTC),
        status=status,
        steps=steps,
        final_output=final_output,
    )


def _run_valid_refund(input_text: str, steps: list[dict[str, object]]) -> str:
    steps.append(
        {
            "type": "model_call",
            "model": OFFLINE_MODEL_NAME,
            "input": input_text,
            "output_text": "I will look up the order before issuing a refund.",
            "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "ORD-123"}}],
        }
    )
    order = lookup_order("ORD-123")
    steps.append(
        {
            "type": "tool_call",
            "tool_name": "lookup_order",
            "arguments": {"order_id": "ORD-123"},
            "result": order,
        }
    )
    steps.append(
        {
            "type": "model_call",
            "model": OFFLINE_MODEL_NAME,
            "input": str(order),
            "output_text": "The order is eligible. I will issue the refund.",
            "tool_calls": [
                {
                    "name": "issue_refund",
                    "arguments": {"order_id": "ORD-123", "reason": "Item arrived broken"},
                }
            ],
        }
    )
    refund = issue_refund("ORD-123", "Item arrived broken")
    steps.append(
        {
            "type": "tool_call",
            "tool_name": "issue_refund",
            "arguments": {"order_id": "ORD-123", "reason": "Item arrived broken"},
            "result": refund,
        }
    )
    return "Refund issued for ORD-123 because the item arrived broken."


def _run_missing_order_id_regression(input_text: str, steps: list[dict[str, object]]) -> str:
    steps.append(
        {
            "type": "model_call",
            "model": OFFLINE_MODEL_NAME,
            "input": input_text,
            "output_text": "I will look up the customer, then take care of the refund.",
            "tool_calls": [{"name": "lookup_customer", "arguments": {"email_or_phone": "unknown"}}],
        }
    )
    customer = lookup_customer("unknown")
    steps.append(
        {
            "type": "tool_call",
            "tool_name": "lookup_customer",
            "arguments": {"email_or_phone": "unknown"},
            "result": customer,
        }
    )
    refund = issue_refund("UNKNOWN", "Customer requested refund without order id")
    steps.append(
        {
            "type": "tool_call",
            "tool_name": "issue_refund",
            "arguments": {
                "order_id": "UNKNOWN",
                "reason": "Customer requested refund without order id",
            },
            "result": refund,
        }
    )
    return "I issued the refund even though the order id was missing."
