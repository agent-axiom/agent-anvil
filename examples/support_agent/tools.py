from __future__ import annotations

from typing import Any


def lookup_customer(email_or_phone: str) -> dict[str, Any]:
    if email_or_phone == "unknown":
        return {"status": "needs_more_info"}
    return {"status": "found", "customer_id": "cus_123"}


def lookup_order(order_id: str) -> dict[str, Any]:
    if order_id == "ORD-123":
        return {
            "status": "found",
            "order_id": order_id,
            "customer_id": "cus_123",
            "eligible_for_refund": True,
        }
    return {"status": "not_found", "order_id": order_id}


def issue_refund(order_id: str, reason: str) -> dict[str, Any]:
    return {"status": "refunded", "order_id": order_id, "reason": reason}


def escalate_to_human(reason: str) -> dict[str, Any]:
    return {"status": "escalated", "reason": reason}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "lookup_customer",
        "description": "Looks up a customer by email or phone number.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "email_or_phone": {
                    "type": "string",
                    "description": "Customer email address or phone number.",
                }
            },
            "required": ["email_or_phone"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "lookup_order",
        "description": "Looks up an order by order id.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order id, such as ORD-123."}
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "issue_refund",
        "description": "Issues a refund to a customer.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order id to refund."},
                "reason": {"type": "string", "description": "Short refund reason."},
            },
            "required": ["order_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "escalate_to_human",
        "description": "Escalates a support conversation to a human agent.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Escalation reason."}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]
