from __future__ import annotations

import re
from typing import Any

ORDER_ID_RE = re.compile(r"\bORD-\d+\b")
MODEL_NAME = "fastapi-demo-agent"


def handle_anvil(payload: dict[str, Any]) -> dict[str, Any]:
    input_text = str(payload.get("input", ""))
    order_id = _extract_order_id(input_text)
    if order_id is None:
        return {
            "status": "completed",
            "events": [
                {
                    "type": "model_call",
                    "model": MODEL_NAME,
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

    return {
        "status": "completed",
        "events": [
            {
                "type": "model_call",
                "model": MODEL_NAME,
                "input": input_text,
                "output_text": f"I will look up {order_id} before any refund action.",
                "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": order_id}}],
            },
            {
                "type": "tool_call",
                "tool_name": "lookup_order",
                "arguments": {"order_id": order_id},
                "result": {"order_id": order_id, "status": "found", "verified": True},
            },
            {
                "type": "final_output",
                "text": f"Order {order_id} is verified. No refund was issued by this demo agent.",
            },
        ],
    }


def _extract_order_id(input_text: str) -> str | None:
    match = ORDER_ID_RE.search(input_text)
    return match.group(0) if match else None
