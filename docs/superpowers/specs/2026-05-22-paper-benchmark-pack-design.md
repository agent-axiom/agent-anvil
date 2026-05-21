# Paper Benchmark Pack Design

## Goal

Prepare Agent Anvil for a credible arXiv systems preprint by adding a small,
reproducible benchmark pack that compares final-answer evaluation with
trace-aware evaluation across tool-use failure modes.

The paper target is a hybrid systems paper: Agent Anvil is presented as a
trace-first CI harness, backed by a compact empirical study that shows why
trace-level assertions catch failures that final-answer-only checks miss.

## Scope

This first PR is intentionally narrow:

- add reproducible benchmark scenarios under `experiments/`
- add baseline and trace-aware result generation
- add a CLI command that runs the benchmark locally and in CI
- add paper-facing docs with tables, commands, and limitations

This PR does not attempt to make `fix`, `learn`, `fuzz`, or MCP audit
research-grade. Those remain experimental helpers and should be discussed as
future work or engineering accelerators.

## Benchmark Design

The benchmark should cover 3-5 domains with 30-100 total trials. Each scenario
must make a trace-level invariant explicit. Candidate domains:

- refunds: destructive refund before order verification
- tool safety: destructive operation without precondition or approval
- account admin: account deletion or permission change before verification
- operations: restart/scale/pause action before diagnosis or approval
- external protocol: malformed or failing agent traces

For each scenario, Agent Anvil records:

- scenario id and domain
- whether final-output-only evaluation would pass
- whether trace-aware deterministic assertions pass
- whether OpenAI semantic grading passes when enabled
- failure type and severity
- runtime and artifact paths

## Baselines

The first baseline is deliberately simple and reproducible:

- final-answer baseline: final output exists and does not contain obvious error
  terms such as `traceback`, `exception`, or `failed`
- trace-aware Anvil: existing deterministic checks, policies, and assertion DSL

This is not meant to claim a universal benchmark result. It demonstrates a
specific gap: answer-only checks can miss unsafe intermediate tool behavior.

## CLI

Add:

```bash
uv run anvil bench experiments/paper.yaml --offline --out docs/paper/results.json
```

The command should:

- load a benchmark manifest
- run each listed scenario suite
- compute final-answer baseline outcomes from produced traces
- compute Agent Anvil outcomes from existing run results
- write JSON and Markdown summaries

## Artifacts

Add paper-facing docs:

- `docs/paper/artifact.md`: exact reproduction commands
- `docs/paper/results.md`: generated benchmark summary
- `docs/paper/limitations.md`: honest scope and threats to validity

The docs should make clear that this is an early systems artifact, not a
production-grade benchmark leaderboard.

## Testing

Tests should cover:

- benchmark manifest loading
- final-answer baseline classification
- benchmark summary aggregation
- CLI smoke run with offline deterministic grading

The benchmark command must be deterministic in offline mode.

## Success Criteria

The PR is complete when:

- `uv run anvil bench experiments/paper.yaml --offline` works from a clean checkout
- generated results include both final-answer and trace-aware pass rates
- at least one scenario passes the final-answer baseline but fails trace-aware checks
- docs explain how to reproduce the results
- pytest, ruff, ty, and existing GitHub Actions pass
