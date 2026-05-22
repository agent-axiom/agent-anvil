# Agent Anvil Preprint Draft

This directory contains the working arXiv preprint scaffold for Agent Anvil.

The current draft is intentionally conservative: it frames Agent Anvil as a
systems artifact and reports the small reproducible benchmark from
`experiments/paper.yaml`. It should not be submitted as-is without a final
editing pass, a larger related-work review, and a PDF build check.

## Reproduce The Reported Table

```bash
uv run anvil bench experiments/paper.yaml --offline --runs-dir runs/paper-benchmark
```

Expected result:

```text
Total trials: 100
Final-answer baseline pass rate: 100.0% [95% CI: 96.3%, 100.0%]
Trace-aware Agent Anvil pass rate: 30.0% [95% CI: 21.9%, 39.6%]
Answer-only missed failures: 70
Answer-only missed failure rate: 70.0% [95% CI: 60.4%, 78.1%]
```

## Draft Files

- `main.tex`: paper draft
- `references.bib`: initial bibliography
- `../docs/paper/artifact.md`: reproduction instructions
- `../docs/paper/results.md`: generated benchmark table
- `../docs/paper/tables.md`: generated CSV and LaTeX table artifacts
- `../docs/paper/limitations.md`: threats to validity
