# External Agent Adapter Templates v1

## Goal

Make bring-your-own-agent onboarding faster by adding framework-specific JSONL
adapter templates and a tiny helper API for emitting Agent Anvil external trace
events.

## Scope

- Add `anvil.external` helpers for reading stdin payloads and emitting protocol
  JSONL events.
- Add `anvil adapter list`.
- Add `anvil adapter add openai-agents --out ...`.
- Add `anvil adapter add langgraph --out ...`.
- Refuse overwrites unless `--force` is passed.
- Document adapter generation and connect it to conformance checks.

## Out Of Scope

- Adding OpenAI Agents SDK or LangGraph as package dependencies.
- Deep framework trace ingestion.
- Hosted adapter registry.
