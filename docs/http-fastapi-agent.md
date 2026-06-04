# FastAPI HTTP Agent Example

This example shows the HTTP endpoint contract without requiring your agent to be
a subprocess. It is useful when your agent already runs as a web service.

Start the example endpoint:

```bash
uv run --with fastapi --with uvicorn \
  uvicorn examples.http_fastapi_agent.app:app --host 127.0.0.1 --port 8080
```

In another terminal, verify the endpoint contract:

```bash
uv run anvil conformance external-agent --url "http://127.0.0.1:8080/anvil"
```

Then run the scenario suite:

```bash
uv run anvil run scenarios/http_fastapi_agent.yaml --offline
```

The FastAPI app exposes `POST /anvil`. Agent Anvil sends the same scenario
payload used by JSONL agents, and the endpoint returns an `events` list with
`model_call`, `tool_call`, and `final_output` events.

The pure agent logic lives in
[`examples/http_fastapi_agent/agent.py`](../examples/http_fastapi_agent/agent.py).
The FastAPI wrapper lives in
[`examples/http_fastapi_agent/app.py`](../examples/http_fastapi_agent/app.py).
