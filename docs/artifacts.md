# Demo Artifacts

These files show what Agent Anvil produces without requiring a hosted dashboard.

## Core Regression Demo

- [Sample report](demo-report.md)
- [Sample trace](demo-trace.json)
- [Sample repair plan](demo-repair-plan.md)
- [Draft learned regression scenario](learned-regression.yaml)
- [Anvil Learn draft-scenario docs](learn.md)

## Before / After Demo

- [Patched demo report](patched-demo-report.md)
- [Patched demo trace](patched-demo-trace.json)

## OpenAI Demo

- [OpenAI demo report](openai-demo-report.md)
- [OpenAI clarification trace](openai-demo-trace.json)
- [OpenAI tool-call trace](openai-demo-tool-trace.json)
- [OpenAI demo repair plan](openai-demo-repair-plan.md)
- [OpenAI-graded regression report](openai-graded-regression-report.md)
- [OpenAI-graded regression repair plan](openai-graded-regression-repair-plan.md)
- [OpenAI-graded regression trace](openai-graded-regression-trace.json)

## Tool Safety Helpers

- [Tool-safety report](tool-safety-report.md)
- [Tool-safety repair plan](tool-safety-repair-plan.md)
- [Mutated refund scenarios](refund-agent-fuzzed.yaml)

## Paper Benchmark

- [Paper benchmark artifact](paper/artifact.md)
- [Paper benchmark results](paper/results.md)
- [Paper benchmark tables](paper/tables.md)
- [Paper benchmark limitations](paper/limitations.md)
- [Leaderboard submission guide](leaderboard.md)
- [Preprint draft](../paper/main.tex)

## MCP Tool Safety Audit

- [MCP tool audit](mcp-audit.md)
- [MCP tool repair plan](mcp-repair.md)
- [Generated MCP safety scenarios](mcp-tool-safety.yaml)
- [MCP audit guide](mcp.md)
- [Limits and experimental helpers](limits.md)

## Reference Docs

- [3-minute judges guide](judges-guide.md)
- [Trust Center](trust.md)
- [Security policy](../SECURITY.md)
- [Data privacy](privacy.md)
- [Stable contracts and schemas](contracts.md)
- [Stability and compatibility](stability.md)
- [Schema versioning](schema-versioning.md)
- [Release provenance](release-provenance.md)
- [Project bootstrap guide](init.md)
- [Scenario packs](packs.md)
- [Trace ingest](ingest.md)
- [Scenario authoring guide](scenarios.md)
- [External agent protocol](protocol.md)
- [External agent conformance](conformance.md)
- [External agent conformance report](conformance-report.md)
- [External agent adapters](adapters.md)
- [FastAPI HTTP agent example](http-fastapi-agent.md)
- [Node / Express HTTP agent example](node-http-agent.md)
- [OpenAI Agents SDK HTTP agent example](openai-agents-sdk-agent.md)
- [Engineering details](engineering.md)
- [GitHub Action marketplace notes](marketplace.md)
- [Leaderboard submission workflow](examples/leaderboard-submission-workflow.yml)
- [Leaderboard index workflow](examples/leaderboard-index-workflow.yml)
- [Hugging Face leaderboard Space scaffold](../integrations/huggingface/leaderboard_space/README.md)
- [Assurance evidence trust](assurance-trust.md)
- [Assurance release contract schema](../schemas/assurance.anvil.dev.release-contract.v1alpha1.schema.json)
- [Assurance evidence record schema](../schemas/assurance.anvil.dev.evidence-record.v1alpha1.schema.json)
- [Trace JSON Schema](../schemas/anvil.trace.v1.schema.json)
- [Scenario JSON Schema](../schemas/anvil.scenario.v1.schema.json)
- [Results JSON Schema](../schemas/anvil.results.v1.schema.json)
- [Run manifest JSON Schema](../schemas/anvil.run_manifest.v1.schema.json)
- [Compare result JSON Schema](../schemas/anvil.compare.result.v1.schema.json)
- [Leaderboard submission JSON Schema](../schemas/agent-anvil.leaderboard.v1.schema.json)
- [Leaderboard index JSON Schema](../schemas/agent-anvil.leaderboard.index.v1.schema.json)
- [Leaderboard GitHub run verification JSON Schema](../schemas/agent-anvil.leaderboard.github_run_verification.v1.schema.json)
- [Leaderboard artifact attestation verification JSON Schema](../schemas/agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json)
- [Leaderboard audit JSON Schema](../schemas/agent-anvil.leaderboard.audit.v1.schema.json)

## Assurance Evidence Artifacts

An Assurance evidence record is metadata around bytes kept in a local
content-addressed run store. `content.sha256` identifies those bytes.
`evidenceId` identifies the canonical record metadata, including observation
time, source, release binding, parents, correlations, and redaction metadata.

Content references use normalized relative POSIX paths. Verification resolves
the path inside the configured store, then opens each component relative to the
trusted store descriptor with symlink following disabled on supported POSIX
systems. It checks the declared and opened-file size, performs a bounded
streaming SHA-256 read, and rejects traversal, symlink races, and content larger
than the configurable 64 MiB default. Parent IDs derive an inspectable directed
graph; duplicate, dangling, self-referential, and cyclic relationships are
rejected. Correlations are identifiers for joining evidence, not proof of
causality.

Verification order is record identity, expected release and contract binding,
trusted ingestion-source comparison, trust assignment, content containment and
digest, then graph and requirement checks. `VerifiedContent.path` is
informational: consumers must not reopen that path and treat later bytes as the
already verified object. A future runner must parse from the verified descriptor
or first copy bytes into an immutable content-addressed object. Raw evidence
remains local unless a user intentionally publishes it.
