# Node / Express HTTP Agent Example v1

## Goal

Show that Agent Anvil's HTTP agent protocol works for non-Python agents by
adding a runnable Node / Express example.

## Scope

- Add a pure Node handler that returns Agent Anvil `events`.
- Add an Express server exposing `POST /anvil`.
- Add `scenarios/node_http_agent.yaml` targeting `http://127.0.0.1:8081/anvil`.
- Document install, start, conformance, and scenario run commands.
- Keep Node dependencies local to the example package, not Python core deps.

## Verification

- Python tests execute the pure Node handler through `node` when available.
- Scenario-loader test verifies the HTTP config.
- Documentation test verifies README/artifact links and copy-paste commands.
- Full ruff, ty, and pytest coverage gate before merge.
