# HTTP Agent Conformance v1

## Goal

Extend `anvil conformance external-agent` so users can validate already-running
HTTP endpoint agents before adding them to a full scenario suite.

## Scope

- Add `--url` as an alternative to `--agent-command`.
- Add repeatable `--header KEY=VALUE` for HTTP request headers with environment
  expansion handled by the existing HTTP runner.
- Reuse `run_external_agent_conformance` and `run_external_agent` so conformance
  and scenario runs share the same trace parsing and protocol-failure behavior.
- Reject ambiguous CLI usage when both `--agent-command` and `--url` are passed.
- Keep conformance as a contract check, not an eval or OpenAI grading step.

## Verification

- Unit tests for passing HTTP endpoint conformance.
- Unit tests for HTTP status failures.
- Unit tests for malformed `--header` values and ambiguous targets.
- Documentation tests for HTTP conformance examples.
