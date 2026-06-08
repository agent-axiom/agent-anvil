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

The trace format keeps `steps` JSON-compatible for easy ingestion from external
agents, but the Python model now validates common event shapes with typed
Pydantic step models. Supported typed events include `model_call`, `tool_call`,
`function_call_output`, protocol errors, tool argument errors, tool execution
errors, and final-output events. The on-disk JSON shape remains stable for
existing artifacts. New traces include `schema_version: anvil.trace.v1`, while
legacy traces without that field still load as v1 artifacts.

## Outcome Taxonomy

Benchmark and paper artifacts classify trials into stable outcome categories:

- `pass`
- `protocol_error`
- `policy_violation`
- `assertion_failure`
- `deterministic_failure`
- `semantic_failure`
- `unknown_failure`

This keeps paper tables and CI summaries from depending on ad hoc failure text.

## Assertion Language

Current scenarios cover expected tools, forbidden tools, required arguments,
clarification, max steps, policy preconditions, ordered tool calls, exact tool
sequences, max tool call counts, min tool call counts, required and forbidden
argument values via simple JSON paths, simple JSON-path checks over tool
results, final-output contains/not-contains checks, trace metric budgets for
latency, token counts, model/tool call counts, and estimated cost, explicit tool
argument/execution error absence checks, and retry-after-tool-error checks.
Planned assertions include richer JSONPath support, backoff timing checks,
conditional assertions, and stronger flaky-run classification.
