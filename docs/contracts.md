# Stable Contracts

Agent Anvil's public integration surface is built around explicit contracts:
scenario files, trace artifacts, external JSONL events, leaderboard submissions,
and generated reports.

## Export JSON Schemas

Export the current stable JSON Schema bundle:

```bash
uv run anvil schema export --out schemas
```

The command writes schemas using export metadata version
`anvil.schema.export.v1`:

- [`schemas/anvil.trace.v1.schema.json`](../schemas/anvil.trace.v1.schema.json)
- [`schemas/anvil.scenario.v1.schema.json`](../schemas/anvil.scenario.v1.schema.json)
- [`schemas/anvil.results.v1.schema.json`](../schemas/anvil.results.v1.schema.json)
- [`schemas/anvil.run_manifest.v1.schema.json`](../schemas/anvil.run_manifest.v1.schema.json)
- [`schemas/anvil.doctor.report.v1.schema.json`](../schemas/anvil.doctor.report.v1.schema.json)
- [`schemas/anvil.compare.result.v1.schema.json`](../schemas/anvil.compare.result.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.v1.schema.json`](../schemas/agent-anvil.leaderboard.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.index.v1.schema.json`](../schemas/agent-anvil.leaderboard.index.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.github_run_verification.v1.schema.json`](../schemas/agent-anvil.leaderboard.github_run_verification.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.audit.v1.schema.json`](../schemas/agent-anvil.leaderboard.audit.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.maintainer_rerun.v1.schema.json`](../schemas/agent-anvil.leaderboard.maintainer_rerun.v1.schema.json)

The source of truth remains the Pydantic models in Agent Anvil. Checked-in
schemas are generated from those models and protected by tests.

## Golden Fixtures

Use the fixture set when writing adapters or compatibility checks:

- [`fixtures/contracts/trace-valid.json`](../fixtures/contracts/trace-valid.json)
- [`fixtures/contracts/trace-protocol-error.json`](../fixtures/contracts/trace-protocol-error.json)
- [`fixtures/contracts/scenario-valid.yaml`](../fixtures/contracts/scenario-valid.yaml)
- [`fixtures/contracts/results-valid.json`](../fixtures/contracts/results-valid.json)
- [`fixtures/contracts/run-manifest-valid.json`](../fixtures/contracts/run-manifest-valid.json)
- [`fixtures/contracts/doctor-report-valid.json`](../fixtures/contracts/doctor-report-valid.json)
- [`fixtures/contracts/compare-result-valid.json`](../fixtures/contracts/compare-result-valid.json)
- [`fixtures/contracts/leaderboard-submission-valid.json`](../fixtures/contracts/leaderboard-submission-valid.json)
- [`fixtures/contracts/leaderboard-index-valid.json`](../fixtures/contracts/leaderboard-index-valid.json)
- [`fixtures/contracts/leaderboard-github-run-verification-valid.json`](../fixtures/contracts/leaderboard-github-run-verification-valid.json)
- [`fixtures/contracts/leaderboard-audit-valid.json`](../fixtures/contracts/leaderboard-audit-valid.json)
- [`fixtures/contracts/leaderboard-maintainer-rerun-valid.json`](../fixtures/contracts/leaderboard-maintainer-rerun-valid.json)

These fixtures are intentionally small. They cover the happy path and one
controlled external-agent protocol failure.

## External Agent Conformance

A compatible JSONL command agent should:

1. read one scenario payload from stdin;
2. emit one JSON object per stdout line;
3. use supported stdout event types: `model_call`, `tool_call`, and
   `final_output`;
4. include required fields for each event type;
5. terminate within the configured timeout.

Malformed events must not be hidden. Agent Anvil converts them into controlled
failed traces with `agent_protocol_error` steps where possible.

A compatible HTTP endpoint agent should:

1. accept the same scenario payload as a JSON POST body;
2. return either `steps` plus `final_output`, or an `events` list;
3. use the same event object shapes as JSONL command output;
4. return non-2xx status codes for endpoint-level failures.

## Compatibility Rules

- Optional fields may be added to v1 schemas.
- Required-field removals or semantic changes require migration notes.
- CI exit-code behavior must not change silently.
- Raw traces remain local unless users publish them intentionally.

For the version policy, see [Schema Versioning](schema-versioning.md).
