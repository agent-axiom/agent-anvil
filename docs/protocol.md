# External JSONL Agent Protocol

Agent Anvil can evaluate agents written in any language by spawning an external
command and exchanging JSON over stdin/stdout.

## Scenario Configuration

```yaml
agent:
  command: "python examples/external_jsonl_agent.py"
  protocol: jsonl
```

`command` is split like a shell command. `protocol` currently supports `jsonl`.

## Input

Agent Anvil sends one JSON object to stdin:

```json
{
  "scenario_id": "external_order_lookup",
  "input": "Please check order ORD-123 before issuing any refund.",
  "trial": 1,
  "run_id": "run_20260502_001",
  "max_steps": 8
}
```

## Output Events

The agent writes one JSON object per line to stdout.

### `model_call`

Use this event when your agent asks a model what to do next.

```json
{
  "type": "model_call",
  "model": "my-agent",
  "input": "Please check order ORD-123.",
  "output_text": "I will look up the order.",
  "tool_calls": [
    {
      "name": "lookup_order",
      "arguments": {
        "order_id": "ORD-123"
      }
    }
  ]
}
```

### `tool_call`

Use this event when your agent executes a tool.

```json
{
  "type": "tool_call",
  "tool_name": "lookup_order",
  "arguments": {
    "order_id": "ORD-123"
  },
  "result": {
    "status": "found"
  }
}
```

### `final_output`

Use this event to finish the trace.

```json
{
  "type": "final_output",
  "text": "Order verified."
}
```

## Exit Behavior

- Exit code `0` means the external agent process completed normally.
- Non-zero exit code marks the trace as failed.
- Deterministic and semantic grading still decide whether the scenario passes.
- `anvil run` exits with code `1` when any graded trial fails, which makes it
  suitable for CI.

## Minimal Agent

```python
from __future__ import annotations

import json
import sys

payload = json.loads(sys.stdin.read())
input_text = payload["input"]

print(json.dumps({
    "type": "model_call",
    "model": "my-agent",
    "input": input_text,
    "output_text": "I will look up the order.",
    "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "ORD-123"}}],
}))
print(json.dumps({
    "type": "tool_call",
    "tool_name": "lookup_order",
    "arguments": {"order_id": "ORD-123"},
    "result": {"status": "found"},
}))
print(json.dumps({"type": "final_output", "text": "Order verified."}))
```
