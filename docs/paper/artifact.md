# Agent Anvil Paper Artifact

This directory contains the reproducible benchmark artifact for the Agent Anvil
systems preprint work.

## What It Measures

The benchmark compares two evaluation views over the same agent traces:

- final-answer baseline: checks whether the final response exists and does not
  contain obvious runtime failure terms
- trace-aware Agent Anvil: checks deterministic tool-use assertions, policy
  preconditions, semantic grading output, and failure clustering

The intended claim is narrow: final-answer checks can miss unsafe intermediate
tool behavior that trace-aware checks catch.

## Reproduce Offline

From a clean checkout:

```bash
uv sync --group dev
uv run anvil paper reproduce
```

Expected summary:

```text
Reproduced Agent Anvil paper artifacts
Benchmark: agent_anvil_trace_eval_benchmark
Total trials: 100
Final-answer baseline pass rate: 100.0% [95% CI: 96.3%, 100.0%]
Trace-aware Agent Anvil pass rate: 30.0% [95% CI: 21.9%, 39.6%]
Answer-only missed failures: 70
Answer-only missed failure rate: 70.0% [95% CI: 60.4%, 78.1%]
Results JSON: docs/paper/results.json
Results Markdown: docs/paper/results.md
Tables: docs/paper/tables
Runs: runs/paper-benchmark
Evaluator ablation:
```

The command writes:

- `docs/paper/results.json`
- `docs/paper/results.md`
- `docs/paper/tables.md`
- `docs/paper/tables/*.csv`
- `docs/paper/tables/suite_results.tex`
- `docs/paper/tables/evaluator_ablation.tex`
- trace artifacts under `runs/paper-benchmark/`

Results include stable outcome categories such as `pass`, `policy_violation`,
`assertion_failure`, `deterministic_failure`, and `semantic_failure` so paper
tables do not depend on ad hoc explanation text.
Pass-rate summaries include 95% Wilson confidence intervals for the final-answer
baseline, trace-aware Agent Anvil, and answer-only missed-failure rate.
The generated summary reports 100 total trials, 100.0% final-answer pass rate
[95% CI: 96.3%, 100.0%], 30.0% trace-aware pass rate [95% CI: 21.9%, 39.6%],
and 70 answer-only missed failures.
The evaluator ablation table compares final-answer checks, trace completion,
deterministic assertions, policy checks, and the full trace-aware evaluator over
the same traces.

`runs/` artifacts are intentionally local and are not committed. Re-run the
command to regenerate trace paths referenced in `results.md`.

## Reproduce With OpenAI Grading

Set an API key and omit `--offline`:

```bash
OPENAI_API_KEY=... uv run anvil paper reproduce --openai \
  --runs-dir runs/paper-benchmark-openai
```

OpenAI grading is useful for semantic criteria and repair suggestions. The
paper benchmark keeps the offline path as the default so reviewers can
reproduce the core trace-vs-answer comparison without credentials.

## Files

- `experiments/paper.yaml`: benchmark manifest
- `experiments/scenarios/*.yaml`: scenario suites
- `docs/paper/results.md`: human-readable benchmark summary
- `docs/paper/results.json`: machine-readable benchmark summary
- `docs/paper/limitations.md`: threats to validity and scope limits
