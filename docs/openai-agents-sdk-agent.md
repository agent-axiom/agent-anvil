# OpenAI Agents SDK HTTP Agent Example

This example shows how to wrap an OpenAI Agents SDK agent behind Agent Anvil's
HTTP external-agent protocol.

The Python Agents SDK uses `Agent`, `Runner`, and `@function_tool` to run
tool-using agents. Agent Anvil keeps the CI contract separate: the example HTTP
endpoint converts the SDK run into Anvil `model_call`, `tool_call`, and
`final_output` events.

## Offline protocol smoke test

The example defaults to an offline deterministic mode so the protocol can be
checked without an API key:

```bash
uv run --with fastapi --with uvicorn \
  uvicorn examples.openai_agents_sdk_agent.app:app --host 127.0.0.1 --port 8082
```

In another terminal:

```bash
uv run anvil conformance external-agent --url "http://127.0.0.1:8082/anvil"
uv run anvil run scenarios/openai_agents_sdk_agent.yaml --offline
```

## Real OpenAI Agents SDK run

Install the SDK only for this example run:

```bash
ANVIL_OPENAI_AGENTS_MODE=openai \
uv run --env-file .env --with openai-agents --with fastapi --with uvicorn \
  uvicorn examples.openai_agents_sdk_agent.app:app --host 127.0.0.1 --port 8082
```

Then run the same scenario without `--offline` if you want OpenAI semantic
grading as well:

```bash
uv run --env-file .env anvil run scenarios/openai_agents_sdk_agent.yaml
```

## Files

- [`examples/openai_agents_sdk_agent/agent.py`](../examples/openai_agents_sdk_agent/agent.py)
- [`examples/openai_agents_sdk_agent/app.py`](../examples/openai_agents_sdk_agent/app.py)
- [`scenarios/openai_agents_sdk_agent.yaml`](../scenarios/openai_agents_sdk_agent.yaml)

