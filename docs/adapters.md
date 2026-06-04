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

`openai-agents` generates a starter that imports `Agent` and `Runner`, runs
`Runner.run_sync(...)`, emits one `model_call`, then emits `final_output`.

The template intentionally does not pretend to recover every internal SDK trace
event. If you need exact tool-call events, wrap your local tools and call
`emit_tool_call(...)` after each tool execution, or map your own trace export
into Agent Anvil JSONL.

Reference: [OpenAI Agents SDK running agents](https://openai.github.io/openai-agents-python/running_agents/).

## LangGraph

`langgraph` generates a starter around `StateGraph`, `START`, `END`,
`compile()`, and `graph.invoke(...)`. It expects your graph to return
`final_output` and optionally a `tool_calls` list in state.

Reference: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api).

## Trust Boundary

Generated adapters are source files that run inside your project. Review them
before execution, keep secrets in your own environment, and run conformance in a
sandbox when testing untrusted agents.
