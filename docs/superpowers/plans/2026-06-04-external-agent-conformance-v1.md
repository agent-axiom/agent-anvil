# External Agent Conformance Kit v1

## Goal

Add a small conformance command that lets users verify a bring-your-own external JSONL agent before wiring it into an Agent Anvil scenario suite.

## Scope

- Add `anvil conformance external-agent`.
- Reuse the existing external JSONL runner instead of duplicating protocol parsing.
- Check that the agent process completes, emits valid JSONL events, avoids protocol errors, stays within `max_steps`, and emits a final output.
- Support `--agent-command`, `--cwd`, repeated `--env KEY=VALUE`, `--timeout`, `--max-steps`, and optional Markdown `--out`.
- Add fixture agents and tests for pass, malformed JSONL, missing final output, cwd/env, and malformed env input.
- Document the command in README and protocol/CLI docs.

## Out Of Scope

- Full benchmark execution.
- OpenAI grading.
- Networked or hosted conformance service.
- Language-specific SDK generation.
