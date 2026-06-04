# External Agent Protocol

Agent Anvil can evaluate agents written in any language by either spawning an
external JSONL command or POSTing to an already-running HTTP endpoint.

For JSONL command agents, run the conformance check before wiring them into a
full scenario suite:

```bash
uv run anvil conformance external-agent --agent-command "python my_agent.py"
```

See [External Agent Conformance](conformance.md) for exit codes, report output,
and fixture examples. HTTP endpoint agents are configured directly in scenario
YAML and are smoke-tested with `anvil run`.

## Trust Boundary

Agent Anvil executes configured external commands and can send scenario payloads
to configured HTTP endpoints. Do not run untrusted scenario files, agent
commands, or endpoint targets outside a sandboxed environment.

## JSONL Command Configuration

```yaml
agent:
  command: "python examples/external_jsonl_agent.py"
  protocol: jsonl
  cwd: "."
  env:
    AGENT_MODE: test
```

`command` is split like a shell command. `cwd` is optional and sets the external
process working directory. `env` is optional and is merged into the inherited
environment for that command.

## HTTP Endpoint Configuration

```yaml
agent:
  protocol: http
  url: "http://127.0.0.1:8080/anvil"
  timeout_seconds: 10
  headers:
    Authorization: "Bearer $ANVIL_AGENT_TOKEN"
```

`url` receives a POST request for each trial. `headers` are optional and support
standard environment expansion such as `$ANVIL_AGENT_TOKEN` or
`${ANVIL_AGENT_TOKEN}`.

## Input

Agent Anvil sends the same JSON object to stdin for JSONL commands and as the
HTTP POST body for HTTP endpoints:

```json
{
  "scenario_id": "external_order_lookup",
  "input": "Please check order ORD-123 before issuing any refund.",
  "trial": 1,
  "run_id": "run_20260502_001",
  "max_steps": 8
}
```

## JSONL Output Events

The agent writes one JSON object per line to stdout.
Each event must include a supported `type`. Invalid events are recorded as
`agent_protocol_error` traces instead of crashing the run.

### `model_call`

Use this event when your agent asks a model what to do next.
Required fields: `type`, `model`, `output_text`, `tool_calls`.

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
Required fields: `type`, `tool_name`, `arguments`, `result`.

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
Required fields: `type` and either `text` or `final_output`.

```json
{
  "type": "final_output",
  "text": "Order verified."
}
```

## Exit Behavior

- Exit code `0` means the external agent process completed normally.
- Non-zero exit code marks the trace as failed.
- Malformed JSONL or a command timeout marks the trace as failed and records an
  `agent_protocol_error` event in the trace artifact.
- HTTP non-2xx responses, network errors, timeouts, and malformed JSON responses
  mark the trace as failed and record an `agent_protocol_error` event.
- Deterministic grading checks `trace.status == "completed"`, so failed external
  agent processes fail the scenario even if their partial output looked valid.
- `anvil run` exits with code `1` when any graded trial fails, which makes it
  suitable for CI.

## HTTP Response

HTTP endpoints can return a trace-like object:

```json
{
  "steps": [
    {
      "type": "model_call",
      "model": "my-agent",
      "output_text": "I will look up the order.",
      "tool_calls": []
    }
  ],
  "final_output": "Order verified."
}
```

Or an event list using the same event objects as JSONL command output:

```json
{
  "events": [
    {
      "type": "model_call",
      "model": "my-agent",
      "output_text": "Done.",
      "tool_calls": []
    },
    {
      "type": "final_output",
      "text": "Done."
    }
  ]
}
```

Optional `status` may be `completed` or `failed`.

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
