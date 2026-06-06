# External Agent Adapters

Agent Anvil can evaluate any agent that reads one JSON payload from stdin and
writes JSONL trace events to stdout. Adapter templates make that bridge easier
for common agent frameworks.

List available templates:

```bash
uv run anvil adapter list
```

Generate a template:

```bash
uv run anvil adapter add openai-agents --out adapters/openai_agents_adapter.py
uv run anvil adapter add langgraph --out adapters/langgraph_adapter.py
```

Then edit the generated adapter to call your real agent and verify the protocol:

```bash
uv run anvil conformance external-agent \
  --agent-command "python adapters/openai_agents_adapter.py"
```

## anvil.external

Templates use `anvil.external`, a tiny helper API for protocol-safe JSONL
emission:

```python
from anvil.external import emit_final_output, emit_model_call, emit_tool_call, read_payload

payload = read_payload()
emit_model_call(
    model="my-agent",
    input_text=payload["input"],
    output_text="I will look up the order.",
    tool_calls=[{"name": "lookup_order", "arguments": {"order_id": "ORD-123"}}],
)
emit_tool_call(
    tool_name="lookup_order",
    arguments={"order_id": "ORD-123"},
    result={"status": "found"},
)
emit_final_output("Order verified.")
```

## OpenAI Agents SDK

`openai-agents` generates a starter that follows the checked
[OpenAI Agents SDK HTTP example](openai-agents-sdk-agent.md): it exposes
`handle_anvil(payload)`, supports deterministic offline protocol checks, and
uses `ANVIL_OPENAI_AGENTS_MODE=openai` to run `Agent`, `Runner.run_sync(...)`,
and a wrapped `@function_tool(name_override="lookup_order")`.

The same generated file can be used in JSONL mode:

```bash
uv run anvil conformance external-agent \
  --agent-command "python adapters/openai_agents_adapter.py"
```

Or as an HTTP adapter without changing the file:

```bash
uv run --with fastapi --with uvicorn \
  uvicorn adapters.openai_agents_adapter:create_fastapi_app \
  --factory --host 127.0.0.1 --port 8080
uv run anvil conformance external-agent --url "http://127.0.0.1:8080/anvil"
```

Replace the demo `lookup_order` tool with your production tools. Keep the
wrapper pattern when you need exact `tool_call` events in Agent Anvil traces.

Reference: [OpenAI Agents SDK running agents](https://openai.github.io/openai-agents-python/running_agents/).

## LangGraph

`langgraph` generates a starter with the same JSONL/HTTP shape as the OpenAI
Agents SDK template: it exposes `handle_anvil(payload)`, defaults to
deterministic offline protocol checks, and uses `ANVIL_LANGGRAPH_MODE=langgraph`
to lazily import `langgraph.graph`, build a `StateGraph`, and run
`graph.invoke(...)`.

The same generated file can be used in JSONL mode:

```bash
uv run anvil conformance external-agent \
  --agent-command "python adapters/langgraph_adapter.py"
```

Or as an HTTP adapter:

```bash
uv run --with fastapi --with uvicorn \
  uvicorn adapters.langgraph_adapter:create_fastapi_app \
  --factory --host 127.0.0.1 --port 8080
uv run anvil conformance external-agent --url "http://127.0.0.1:8080/anvil"
```

Replace `agent_node` with your production graph. Keep tool executions in a
`tool_calls` list with `tool_name`, `arguments`, and `result` when you want
exact `tool_call` events in Agent Anvil traces.

Reference: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api).

## Trust Boundary

Generated adapters are source files that run inside your project. Review them
before execution, keep secrets in your own environment, and run conformance in a
sandbox when testing untrusted agents.
