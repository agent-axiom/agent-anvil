# HTTP Python Adapter Template v1

## Goal

Add a framework-free adapter template for users who want to expose any Python
agent through Agent Anvil's JSONL or HTTP external-agent protocol without
installing FastAPI, LangGraph, or OpenAI Agents SDK.

## Scope

- Add `http-python` to `anvil adapter list` and `anvil adapter add`.
- Generate a self-contained adapter using Python stdlib `ThreadingHTTPServer`.
- Keep JSONL mode available by default.
- Add `--serve --host --port` HTTP mode.
- Test generated JSONL output and localhost HTTP response.
- Update adapter docs.

## Verification

- Targeted adapter-template pytest.
- Full ruff, ty, and pytest coverage gate before merge.
