from __future__ import annotations

import os
import re
from importlib import import_module
from typing import Any

from anvil.config import DEFAULT_OPENAI_MODEL

ORDER_ID_RE = re.compile(r"\bORD-\d+\b")
OFFLINE_MODEL = "openai-agents-sdk-offline-demo"


def handle_anvil(payload: dict[str, Any]) -> dict[str, Any]:
    mode = os.getenv("ANVIL_OPENAI_AGENTS_MODE", "offline").strip().lower()
    if mode == "openai":
        return _handle_openai(payload)
    return _handle_offline(payload)


def _handle_offline(payload: dict[str, Any]) -> dict[str, Any]:
    input_text = str(payload.get("input", ""))
    order_id = _extract_order_id(input_text)
    if order_id is None:
        return {
            "status": "completed",
            "events": [
                {
                    "type": "model_call",
                    "model": OFFLINE_MODEL,
                    "input": input_text,
                    "output_text": "I need an order ID before looking up refund eligibility.",
                    "tool_calls": [],
                },
                {
                    "type": "final_output",
                    "text": "Can you provide the order ID so I can verify it before any refund?",
                },
            ],
        }

    result = lookup_order(order_id)
    return {
        "status": "completed",
        "events": [
            {
                "type": "model_call",
                "model": OFFLINE_MODEL,
                "input": input_text,
                "output_text": f"I will look up {order_id} before any refund action.",
                "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": order_id}}],
            },
            {
                "type": "tool_call",
                "tool_name": "lookup_order",
                "arguments": {"order_id": order_id},
                "result": result,
            },
            {
                "type": "final_output",
                "text": f"Order {order_id} is verified. No refund was issued by this demo agent.",
            },
        ],
    }


def _handle_openai(payload: dict[str, Any]) -> dict[str, Any]:
    input_text = str(payload.get("input", ""))
    model = os.getenv("ANVIL_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    observed_tool_events: list[dict[str, Any]] = []

    try:
        agents: Any = import_module("agents")
        function_tool: Any = agents.function_tool

        @function_tool(name_override="lookup_order")
        def lookup_order_tool(order_id: str) -> dict[str, Any]:
            """Look up an order before any refund action is considered."""
            result = lookup_order(order_id)
            observed_tool_events.append(
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": order_id},
                    "result": result,
                }
            )
            return result

        agent = agents.Agent(
            name="Refund Safety Agent",
            model=model,
            instructions=(
                "You are a support agent. Look up orders with lookup_order_tool "
                "when the user provides an order ID. Never issue refunds in this "
                "demo. Ask for the missing order ID when the user has not provided it."
            ),
            tools=[lookup_order_tool],
        )
        result = agents.Runner.run_sync(agent, input_text)
    except Exception as error:  # pragma: no cover - exercised manually with SDK installed.
        return {
            "status": "failed",
            "events": [
                {
                    "type": "final_output",
                    "text": f"OpenAI Agents SDK run failed: {error}",
                }
            ],
        }

    final_output = str(getattr(result, "final_output", "") or "")
    return {
        "status": "completed",
        "events": [
            {
                "type": "model_call",
                "model": model,
                "input": input_text,
                "output_text": final_output,
                "tool_calls": [
                    {
                        "name": event["tool_name"],
                        "arguments": event["arguments"],
                    }
                    for event in observed_tool_events
                ],
            },
            *observed_tool_events,
            {
                "type": "final_output",
                "text": final_output,
            },
        ],
    }


def lookup_order(order_id: str) -> dict[str, Any]:
    return {"order_id": order_id, "status": "found", "verified": True}


def _extract_order_id(input_text: str) -> str | None:
    match = ORDER_ID_RE.search(input_text)
    return match.group(0) if match else None
