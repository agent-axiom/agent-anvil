# Paper Benchmark Limitations

This artifact is an early systems benchmark, not a universal leaderboard for
agent evaluation.

## Scope Limits

- The benchmark uses compact deterministic demo agents so the offline path is
  reproducible in CI.
- The final-answer baseline is intentionally simple. It represents a common
  weak evaluation pattern, not the strongest possible answer-only judge.
- The scenario set is small: 3 suites, 6 scenario cases, 30 total trials.
- Most failures are synthetic but realistic workflow bugs: premature
  destructive tools, missing preconditions, hallucinated identifiers, and
  unsafe retries.

## Grader Limits

- Offline semantic grading is a heuristic smoke check.
- OpenAI semantic grading is optional and can vary with model behavior.
- Repair, learn, fuzz, and MCP hardening helpers are scaffolding tools, not
  proof-generating systems.

## Trace Limits

- The benchmark assumes agents can emit or be adapted into Agent Anvil traces.
- Local run artifacts may contain raw tool arguments and results. Redaction is
  applied before OpenAI grading, but teams should still review traces before
  sharing them externally.
- Trace schema compatibility is currently maintained at the Agent Anvil JSON
  artifact level; richer cross-framework trace adapters are future work.

## Interpretation

The main result should be read as:

> In these tool-use scenarios, final-answer-only checks mark all trials as
> passing, while trace-aware checks expose unsafe intermediate behavior.

It should not be read as:

> Agent Anvil is a complete production-grade replacement for hosted agent
> observability, formal verification, or human domain review.
