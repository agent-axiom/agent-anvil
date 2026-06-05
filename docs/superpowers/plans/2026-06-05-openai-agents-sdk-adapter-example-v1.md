# OpenAI Agents SDK Adapter Example v1

## Goal

Show that Agent Anvil can evaluate an OpenAI Agents SDK agent through the same
HTTP external-agent protocol used by other frameworks.

## Scope

- Add `examples/openai_agents_sdk_agent` with an offline-safe handler.
- Add a real `ANVIL_OPENAI_AGENTS_MODE=openai` path using `Agent`,
  `Runner.run_sync`, and `@function_tool`.
- Add a FastAPI HTTP endpoint on port 8082.
- Add `scenarios/openai_agents_sdk_agent.yaml`.
- Document offline conformance and real OpenAI Agents SDK execution.

## Verification

- Targeted pytest for the offline handler, scenario config, and docs.
- Full ruff, ty, and pytest coverage gate before merge.
