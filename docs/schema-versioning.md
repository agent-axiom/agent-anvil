# Schema Versioning

Agent Anvil uses explicit schema identifiers for persisted artifacts that are
intended to cross process, repository, or CI boundaries.

For export commands, checked-in JSON Schemas, and golden fixtures, see
[Stable Contracts](contracts.md).

## Trace Schema

Current trace artifacts use:

```json
{
  "schema_version": "anvil.trace.v1"
}
```

`anvil.trace.v1` includes run metadata, scenario metadata, typed model/tool
steps, final output, status, and metrics. Legacy traces without a
`schema_version` are treated as v1-compatible artifacts where possible.

Compatible v1 changes may add optional fields. Incompatible changes require a
new schema version and migration notes.

## Results Schema

Persisted run result artifacts use:

```json
{
  "schema_version": "anvil.results.v1"
}
```

`anvil.results.v1` includes suite metadata, aggregate trial summaries, flaky
scenario summaries, per-trial grades, and failure clusters. Legacy
`results.json` files without `schema_version` are still read as JSON artifacts
by report, compare, and PR-comment commands.

## Compare Result Schema

Machine-readable compare artifacts use:

```json
{
  "schema_version": "anvil.compare.result.v1"
}
```

This schema is intended for CI bots and PR comments that consume
`anvil compare --json` or `anvil compare --out compare.json`.

## Leaderboard Submission Schema

Leaderboard submissions use:

```json
{
  "schema_version": "agent-anvil.leaderboard.v1"
}
```

The public leaderboard index uses:

```json
{
  "schema_version": "agent-anvil.leaderboard.index.v1"
}
```

These schemas are designed for aggregate public reporting. They should not
include raw traces, model outputs, tool results, secrets, or private scenario
content.

## Scenario Files

Scenario files are YAML and are validated by Pydantic models with
`extra="forbid"` for the core configuration. Unknown fields should fail fast
instead of being silently ignored.

Scenario compatibility guidance:

- adding optional fields is compatible;
- tightening validation should include a migration note;
- changing assertion semantics is breaking unless guarded by a new assertion
  type or explicit versioned behavior;
- policy behavior that affects CI exit codes must be called out in release
  notes.

## External JSONL Protocol

The external JSONL protocol is intentionally small:

- Agent Anvil sends one JSON scenario payload on stdin.
- The agent emits JSONL events on stdout.
- Supported event types include `model_call`, `tool_call`, protocol/tool errors,
  and `final_output`.

Protocol changes should preserve old event shapes where practical. Unknown or
malformed events should become controlled protocol failures with trace artifacts.

## Migration Rules

When a schema changes, release notes should include:

- affected schema identifier;
- whether the change is compatible;
- example old and new shapes;
- whether existing `runs/` artifacts still load;
- recommended migration command or manual edit, if needed.

The checked-in schema export bundle is generated with:

```bash
uv run anvil schema export --out schemas
```
