# LangGraph Template HTTP Pattern v1

## Goal

Bring `anvil adapter add langgraph` up to the same quality bar as the OpenAI
Agents SDK template.

## Scope

- Add tests for generated template structure and offline execution.
- Update the LangGraph template with `handle_anvil(payload)`.
- Keep deterministic offline mode as the default.
- Add `ANVIL_LANGGRAPH_MODE=langgraph` for real LangGraph runs.
- Add a lazily-created FastAPI app factory for HTTP mode.
- Update adapter docs to explain JSONL and HTTP usage.

## Verification

- Targeted adapter-template pytest.
- Full ruff, ty, and pytest coverage gate before merge.
