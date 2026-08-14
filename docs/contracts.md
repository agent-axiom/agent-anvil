# Stable Contracts

Agent Anvil's public integration surface is built around explicit contracts:
scenario files, trace artifacts, external JSONL events, leaderboard submissions,
and generated reports.

## Export JSON Schemas

Export the current stable JSON Schema bundle:

```bash
uv run anvil schema export --out schemas
uv run anvil schema validate leaderboard_submission.json
uv run anvil schema validate scenarios/refund_agent.yaml --schema anvil.scenario.v1
uv run anvil schema validate-dir submissions
uv run anvil schema validate-dir maintainer_reruns \
  --schema agent-anvil.leaderboard.maintainer_rerun.v1
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
- [`schemas/agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json`](../schemas/agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.audit.v1.schema.json`](../schemas/agent-anvil.leaderboard.audit.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.evidence_index.v1.schema.json`](../schemas/agent-anvil.leaderboard.evidence_index.v1.schema.json)
- [`schemas/agent-anvil.leaderboard.maintainer_rerun.v1.schema.json`](../schemas/agent-anvil.leaderboard.maintainer_rerun.v1.schema.json)
- [`schemas/assurance.anvil.dev.release-contract.v1alpha1.schema.json`](../schemas/assurance.anvil.dev.release-contract.v1alpha1.schema.json)
- [`schemas/assurance.anvil.dev.evidence-record.v1alpha1.schema.json`](../schemas/assurance.anvil.dev.evidence-record.v1alpha1.schema.json)

The source of truth remains the Pydantic models in Agent Anvil. Checked-in
schemas are generated from those models and protected by Draft 2020-12 tests
for runtime invariants that Pydantic cannot infer automatically.

Use `schema validate-dir` in submission repositories when maintainers need a
cheap contract gate before slower GitHub API checks, leaderboard rebuilds, or
manual reruns. The command validates `*.json` files by default, can apply one
explicit schema to every matched file with `--schema`, and can traverse nested
evidence folders with `--recursive`.

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
- [`fixtures/contracts/leaderboard-artifact-attestation-verification-valid.json`](../fixtures/contracts/leaderboard-artifact-attestation-verification-valid.json)
- [`fixtures/contracts/leaderboard-audit-valid.json`](../fixtures/contracts/leaderboard-audit-valid.json)
- [`fixtures/contracts/leaderboard-evidence-index-valid.json`](../fixtures/contracts/leaderboard-evidence-index-valid.json)
- [`fixtures/contracts/leaderboard-maintainer-rerun-valid.json`](../fixtures/contracts/leaderboard-maintainer-rerun-valid.json)
- [`fixtures/contracts/assurance-release-contract-valid.yaml`](../fixtures/contracts/assurance-release-contract-valid.yaml)
- [`fixtures/contracts/assurance-evidence-record-valid.json`](../fixtures/contracts/assurance-evidence-record-valid.json)

These fixtures are intentionally small. They cover the happy path and one
controlled external-agent protocol failure.

## Assurance Alpha Contracts

The Assurance foundation is additive and experimental. It does not change
`anvil.scenario.v1`, current trace artifacts, or `anvil run` behavior.

The release envelope uses
`assurance.anvil.dev/release-contract/v1alpha1`. Validate its YAML fixture with
an explicit schema ID:

```bash
uv run anvil schema validate \
  fixtures/contracts/assurance-release-contract-valid.yaml \
  --schema assurance.anvil.dev/release-contract/v1alpha1
```

The evidence envelope uses
`assurance.anvil.dev/evidence-record/v1alpha1`. Its `schemaVersion` is
auto-detected from JSON:

```bash
uv run anvil schema validate \
  fixtures/contracts/assurance-evidence-record-valid.json
```

Schema validation checks document shape. Evidence identity, content digest,
store containment, source trust assignment, release binding, and parent graph
integrity require the verification APIs in `anvil.assurance`. Parsing a record
that claims `L3` does not verify that claim. See
[Assurance Evidence Trust](assurance-trust.md).

Release-contract YAML is decoded as UTF-8 with default limits of 1 MiB, 50,000
nodes, and 100 levels of nesting. The parser accepts only string mapping keys
and rejects duplicate YAML keys, tagged-key ambiguity, and YAML aliases before model
validation, preventing last-key-wins ambiguity and alias expansion. Assurance
evidence JSON and schema auto-detection use the same 1 MiB byte ceiling; all JSON
contracts reject duplicate keys and enforce the node and depth budgets. Explicitly
selected legacy JSON schemas retain their existing unbounded byte compatibility, so
use auto-detection or an external artifact-size gate for untrusted unknown inputs.
Contract readers open paths nonblocking and reject anything that does not resolve to
a regular file; FIFOs, sockets, devices, and directories cannot stall validation.
Assurance task inputs, check configuration, and component metadata accept only
canonical finite JSON values. Component metadata also rejects secret-like keys;
credentials belong in the execution environment, never in release contracts.

Check definitions are data, not import instructions. Loading a contract without
a `CheckTypeRegistry` performs inspection-only envelope validation. Any future
runner or verdict path must supply an explicit registry and reject undeclared,
unregistered, or version-incompatible packs; contract data never drives dynamic
imports.

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
