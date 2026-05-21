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
uv run anvil bench experiments/paper.yaml --offline --runs-dir runs/paper-benchmark
```

Expected summary:

```text
Benchmark: agent_anvil_trace_eval_benchmark
Total trials: 100
Final-answer baseline pass rate: 100.0%
Trace-aware Agent Anvil pass rate: 30.0%
Answer-only missed failures: 70
```

The command writes:

- `docs/paper/results.json`
- `docs/paper/results.md`
- trace artifacts under `runs/paper-benchmark/`

Results include stable outcome categories such as `pass`, `policy_violation`,
`assertion_failure`, `deterministic_failure`, and `semantic_failure` so paper
tables do not depend on ad hoc explanation text.

`runs/` artifacts are intentionally local and are not committed. Re-run the
command to regenerate trace paths referenced in `results.md`.

## Reproduce With OpenAI Grading

Set an API key and omit `--offline`:

```bash
OPENAI_API_KEY=... uv run anvil bench experiments/paper.yaml \
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
