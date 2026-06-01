# Trust Center

Agent Anvil's trust model is simple: keep eval execution local, keep artifacts
inspectable, make network calls explicit, and label experimental helpers
honestly.

## Stable Core

The stable core is the trace-first CI eval loop:

```text
scenario -> agent run -> trace -> deterministic checks -> optional OpenAI grading -> report -> CI
```

The stable core includes:

- YAML scenario loading;
- deterministic assertions and policy checks;
- trace recording and persisted run artifacts;
- OpenAI semantic grading with default redaction;
- Markdown/JSON reports and repair plans;
- external JSONL agent protocol;
- GitHub Action integration;
- public leaderboard submission validation.

## Experimental Helpers

Experimental Helpers are useful scaffolding, not guarantees:

- `anvil fix` generates reviewable patch suggestions, with demo-specific
  behavior for the bundled refund agent.
- `anvil learn` creates a draft regression scenario from a trace.
- `anvil fuzz` creates deterministic scenario mutations.
- `anvil mcp audit` and `anvil mcp harden` lint MCP tool descriptions and draft
  safety scenarios.

Production users should review helper output before committing it.

## Trust Documents

- [Security Policy](../SECURITY.md)
- [Data Privacy](privacy.md)
- [Stability and Compatibility](stability.md)
- [Schema Versioning](schema-versioning.md)
- [Release Provenance](release-provenance.md)
- [Limits and Experimental Helpers](limits.md)

## User-Controlled Boundaries

Agent Anvil does not run hosted infrastructure for your private traces. You run
the CLI locally or in your CI. You decide whether to:

- run with `--offline`;
- call OpenAI semantic grading;
- publish run artifacts;
- export a leaderboard submission;
- execute an external agent command.

The public leaderboard accepts aggregate submissions only. It does not require
raw traces, tool outputs, secrets, or scenario content with private data.

## What Trust Does Not Mean

Agent Anvil does not claim to prevent all benchmark gaming, prove agent safety,
or sandbox arbitrary code. It provides inspectable traces, deterministic
invariants, semantic grading, and reproducible artifacts so teams can catch and
discuss agent regressions with evidence.
