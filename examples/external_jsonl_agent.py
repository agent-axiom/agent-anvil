from __future__ import annotations

import json
import sys


def main() -> None:
    payload = json.loads(sys.stdin.read())
    input_text = str(payload["input"])
    order_id = "ORD-123" if "ORD-123" in input_text else "UNKNOWN"

    emit(
        {
            "type": "model_call",
            "model": "external-jsonl-demo",
            "input": input_text,
            "output_text": "I will look up the order before taking action.",
            "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": order_id}}],
        }
    )
    emit(
        {
            "type": "tool_call",
            "tool_name": "lookup_order",
            "arguments": {"order_id": order_id},
            "result": {"status": "found" if order_id == "ORD-123" else "not_found"},
        }
    )
    emit({"type": "final_output", "text": f"Order lookup completed for {order_id}."})


def emit(event: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
