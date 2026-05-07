# Limits and Experimental Helpers

Agent Anvil's stable core is the trace-first CI eval loop:

```text
scenario -> agent run -> trace -> deterministic checks -> OpenAI grading -> report -> CI
```

The core is designed to catch workflow failures that final-answer evals often
miss: wrong tool choice, wrong arguments, destructive tools too early, missing
clarification, loops, and violated business invariants.

## Production-Useful Core

- YAML scenario suites
- persisted run artifacts
- model/tool trace capture
- deterministic checks for tool use and policy preconditions
- OpenAI structured semantic grading
- failure clustering by type and severity
- Markdown/JSON reports
- GitHub Action integration

## Experimental Helpers

These commands are useful scaffolding, but intentionally conservative:

- `anvil fix` generates a reviewable patch from the current repair signal. The
  bundled refund demo includes demo-specific patch behavior; do not treat it as
  a generic auto-fix engine.
- `anvil learn` turns a failing trace into a draft regression scenario. Offline
  mode uses heuristics such as risky tool names and missing/synthetic arguments.
  Review the generated YAML before committing it.
- `anvil fuzz` is a deterministic scenario mutation helper. It is not coverage-
  guided fuzzing or a security fuzzer.
- `anvil mcp audit` and `anvil mcp harden` run static MCP tool-description
  checks and generate draft safety scenarios plus repair hints. They are not a
  full MCP safety analyzer.

## Trace Schema

The current trace format keeps `steps` JSON-compatible for easy ingestion from
external agents. A typed event schema is the next planned hardening step so
adapters can validate `model_call`, `tool_call`, protocol-error, and final-output
events more strictly.

## Assertion Language

Current scenarios cover expected tools, forbidden tools, required arguments,
clarification, max steps, and policy preconditions. Planned assertions include
ordered tool sequences, min/max call counts, forbidden argument values, JSONPath
checks over tool results, latency/cost budgets, and stronger flaky-run
classification.
