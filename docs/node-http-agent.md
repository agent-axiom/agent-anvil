# Node / Express HTTP Agent Example

This example shows that Agent Anvil's HTTP protocol is language-agnostic. The
agent runs as an Express service and returns the same `events` response shape as
the Python FastAPI example.

Install the example dependency:

```bash
npm --prefix examples/node_http_agent install
```

Start the endpoint:

```bash
npm --prefix examples/node_http_agent start
```

In another terminal, verify the endpoint contract:

```bash
uv run anvil conformance external-agent --url "http://127.0.0.1:8081/anvil"
```

Then run the scenario suite:

```bash
uv run anvil run scenarios/node_http_agent.yaml --offline
```

The reusable agent logic lives in
[`examples/node_http_agent/agent.mjs`](../examples/node_http_agent/agent.mjs).
The Express wrapper lives in
[`examples/node_http_agent/server.mjs`](../examples/node_http_agent/server.mjs).
