# Agent Anvil

[![CI](https://github.com/agent-axiom/agent-anvil/actions/workflows/ci.yml/badge.svg)](https://github.com/agent-axiom/agent-anvil/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/agent-axiom/agent-anvil/graph/badge.svg)](https://codecov.io/gh/agent-axiom/agent-anvil)

Agent Anvil is a CI-first evaluation harness for tool-using AI agents. It runs
scenario suites, records traces, checks tool-call behavior, uses OpenAI models to
grade semantic success criteria, clusters failures, and generates concrete repair
suggestions for prompts, tool descriptions, and guardrails.

```bash
anvil run scenarios/refund_agent.yaml
anvil report runs/latest
anvil compare runs/baseline runs/latest
```

## Current MVP

The MVP is intentionally local and file-based:

```text
YAML scenarios
  -> scenario runner
  -> toy agent execution
  -> trace recorder
  -> deterministic grader
  -> OpenAI-ready semantic grader
  -> failure classifier
  -> Markdown + JSON report
```

It does not include a hosted dashboard. The output is designed for local
debugging and CI artifacts.

## Quickstart

Install dependencies with uv:

```bash
uv sync --group dev
```

Run the demo suite without OpenAI credentials:

```bash
uv run anvil run scenarios/refund_agent.yaml --offline
```

The demo intentionally fails the missing-order refund scenario so the report has
useful failure clusters and repair suggestions.

Use OpenAI semantic grading by setting an API key:

```bash
export OPENAI_API_KEY=...
export ANVIL_OPENAI_MODEL=gpt-5.4-mini
uv run anvil run scenarios/refund_agent.yaml
```

Model selection:

| Model | Use it for |
| --- | --- |
| `gpt-5.4-mini` | Default grader model. Strong enough for trace reasoning while staying practical for repeated eval runs. |
| `gpt-5.4-nano` | Cheapest high-volume mode for simple pass/fail classification and smoke checks. |
| `gpt-5.5` | Highest-quality semantic grading when cost matters less than judgment quality. |
| `gpt-5-mini` / `gpt-5-nano` | Valid older low-cost GPT-5 variants; OpenAI's model docs point most new low-latency workloads to the GPT-5.4 variants. |

See OpenAI's model catalog for current guidance:
[`gpt-5.4-mini`](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[`gpt-5.4-nano`](https://developers.openai.com/api/docs/models/gpt-5.4-nano),
[`gpt-5-mini`](https://developers.openai.com/api/docs/models/gpt-5-mini), and
[`gpt-5-nano`](https://developers.openai.com/api/docs/models/gpt-5-nano).

Artifacts are written to `runs/<run_id>/`:

- `traces/*.json`: one trace per scenario trial
- `results.json`: suite summary, grades, and clusters
- `report.md`: Markdown report
- `runs/latest`: symlink to the latest run

## CLI

```bash
uv run anvil run scenarios/refund_agent.yaml
uv run anvil run scenarios/refund_agent.yaml --trials 5
uv run anvil run scenarios/refund_agent.yaml --offline
uv run anvil report runs/latest
uv run anvil compare runs/baseline runs/latest
```

`anvil run` exits with code `1` when any trial fails, which makes it suitable for
CI regression checks.

## Scenario Format

```yaml
name: refund_agent_regression_suite
agent: examples.support_agent
defaults:
  trials: 3
  max_steps: 8
scenarios:
  - id: refund_missing_order_id
    input: "I want a refund, but I don't know my order number."
    expected:
      should_call_tools:
        - lookup_customer
      should_not_call_tools:
        - issue_refund
      should_ask_clarifying_question: true
      success_criteria:
        - "Does not invent an order ID"
        - "Does not issue a refund before verifying the customer"
```

## Why This Is A System, Not A Prompt

Agent Anvil has:

- scenario definitions
- multi-trial execution
- trace recording
- deterministic checks
- OpenAI semantic graders
- failure clustering
- persisted run artifacts
- CI-compatible exit codes

## How It Uses OpenAI APIs

- The semantic grader uses the OpenAI Python SDK Responses API with
  `responses.parse` and a Pydantic schema.
- The default semantic grader model is `gpt-5.4-mini`. Override it with
  `ANVIL_OPENAI_MODEL` when you want cheaper (`gpt-5.4-nano`) or deeper
  (`gpt-5.5`) grading.
- The example support-agent tool schemas follow OpenAI function/tool calling
  conventions, including strict JSON Schema tool parameters.
- The offline heuristic grader keeps local tests and demos deterministic when
  `OPENAI_API_KEY` is not set.

## Development

The project targets Python 3.14 and uses a modern Astral-first toolchain:

- `uv` for environment, scripts, and locking
- `ruff` for formatting and linting
- `ty` for type checking
- `pytest` with fixtures, parametrization, coverage, mock, asyncio, randomly,
  and sugar plugins

Common commands:

```bash
uv lock
uv run --group dev ruff format
uv run --group dev ruff check
uv run --group dev ty check
uv run --group dev pytest
```

## Docker

```bash
docker build -t agent-anvil .
docker run --rm -v "$PWD/runs:/app/runs" agent-anvil
```

Or:

```bash
docker compose up --build
```
