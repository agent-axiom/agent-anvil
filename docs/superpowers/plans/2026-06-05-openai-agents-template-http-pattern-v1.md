# OpenAI Agents Template HTTP Pattern v1

## Goal

Make `anvil adapter add openai-agents` generate a useful adapter that matches
the verified OpenAI Agents SDK HTTP example rather than a JSONL-only sketch.

## Scope

- Add tests for generated template structure and offline execution.
- Update the OpenAI Agents SDK template with `handle_anvil(payload)`.
- Keep deterministic offline mode as the default.
- Add `ANVIL_OPENAI_AGENTS_MODE=openai` for real SDK runs.
- Add a lazily-created FastAPI app factory for HTTP mode.
- Update adapter docs to explain JSONL and HTTP usage.

## Verification

- Targeted adapter-template pytest.
- Full ruff, ty, and pytest coverage gate before merge.
