# FastAPI HTTP Agent Example v1

## Goal

Provide a complete local HTTP endpoint example so users can try the `protocol:
http` path without writing their own web service first.

## Scope

- Add a pure handler that returns Agent Anvil `events`.
- Add a FastAPI wrapper exposing `POST /anvil`.
- Add `scenarios/http_fastapi_agent.yaml` targeting `http://127.0.0.1:8080/anvil`.
- Document a three-command flow: start endpoint, run conformance, run scenario.
- Avoid adding FastAPI and uvicorn as core Agent Anvil dependencies.

## Verification

- Unit tests for the pure handler's event response shape.
- Scenario-loader test for the HTTP example scenario.
- Documentation test for the bundled FastAPI example.
- Full ruff, ty, and pytest coverage gate before merge.
