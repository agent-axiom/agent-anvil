# Agent Anvil

[![CI](https://github.com/agent-axiom/agent-anvil/actions/workflows/ci.yml/badge.svg)](https://github.com/agent-axiom/agent-anvil/actions/workflows/ci.yml)
[![Agent Anvil](https://github.com/agent-axiom/agent-anvil/actions/workflows/agent-anvil.yml/badge.svg)](https://github.com/agent-axiom/agent-anvil/actions/workflows/agent-anvil.yml)
![coverage](https://img.shields.io/badge/coverage-%E2%89%A590%25-brightgreen)
[![release](https://img.shields.io/github/v/release/agent-axiom/agent-anvil)](https://github.com/agent-axiom/agent-anvil/releases)
![python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![openai](https://img.shields.io/badge/OpenAI-Responses%20API-412991)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Agent Anvil is a CI-first evaluation harness for tool-using AI agents.

Most evals ask: "was the final answer good?" Agent Anvil asks: "did the
agent behave safely while getting there?"

It runs YAML scenario suites, records model/tool traces, checks trace completion,
tool choice, arguments, clarification behavior, and policy preconditions, uses
OpenAI models for semantic grading, clusters failures, and writes concrete
prompt/tool/guardrail repair plans.

It catches workflow bugs final-answer evals miss: wrong tools, wrong arguments,
destructive tools called too early, missing clarifying questions, loops, and
violated business invariants.

Scenarios can use a deterministic assertion DSL for trace invariants such as
ordered tool calls, max call counts, forbidden argument values, tool-result
checks, and final-output text checks.

```bash
uv run anvil init --agent-command "python my_agent.py"
uv run anvil run scenarios/external_jsonl_agent.yaml --offline
uv run anvil report runs/latest
uv run anvil summary runs/latest --github
```

![Agent Anvil catching a premature tool call](docs/demo.svg)

## 30-Second Demo

Agent Anvil's core loop is intentionally small:

```text
run -> trace -> check -> grade -> report -> CI
```

One-command demo:

```bash
./scripts/demo.sh
```

```bash
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1 || true
uv run anvil repair runs/latest
```

For review, see the [3-minute judges guide](docs/judges-guide.md). For the
challenge post, see [submission text](docs/submission.md).

## What It Catches

The bundled refund-agent demo intentionally fails one scenario:

> A customer asks for a refund without an order number. The agent looks up the
> customer, then calls `issue_refund` with `order_id="UNKNOWN"` before verifying
> the order.

Agent Anvil flags the forbidden destructive tool call, clusters it as
`premature_tool_execution`, and suggests patches for the prompt, tool
description, and guardrail.

That gives a concrete eval loop:

1. weak tool description: `issue_refund` issues a refund to a customer
2. failing trace: agent calls `issue_refund(order_id="UNKNOWN")`
3. repair plan: require `lookup_order` verification before destructive tools
4. CI status: fail the build and link the first bad trace
5. next run: patched prompts/tools can be compared against the baseline

Start here:

- [3-minute judges guide](docs/judges-guide.md)
- [Sample report](docs/demo-report.md)
- [Sample repair plan](docs/demo-repair-plan.md)
- [OpenAI-graded regression report](docs/openai-graded-regression-report.md)
- [Limits and experimental helpers](docs/limits.md)
- [MCP tool safety audit](docs/mcp.md)
- [Paper benchmark artifact](docs/paper/artifact.md)
- [Leaderboard submissions](docs/leaderboard.md)
- [Full artifact index](docs/artifacts.md)
- [CLI reference](docs/cli.md)

## How It Works

```mermaid
flowchart LR
    A["YAML scenarios"] --> B["Scenario runner"]
    B --> C["Demo or external agent"]
    C --> D["Trace recorder"]
    D --> E["Deterministic checks"]
    D --> P["Policy guardrails"]
    D --> F["OpenAI semantic grader"]
    E --> G["Failure clustering"]
    P --> G
    F --> G
    G --> H["Markdown + JSON report"]
    G --> I["Repair plan"]
```

## Quickstart

Install dependencies:

```bash
uv sync --group dev
```

Run the deterministic demo without OpenAI credentials:

```bash
uv run anvil run scenarios/external_jsonl_agent.yaml --offline
```

Run the intentional regression demo and inspect the repair plan:

```bash
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1 || true
uv run anvil repair runs/latest
```

Optional helper commands can turn the failing trace into a reviewable demo patch
and a draft regression scenario. These are scaffolding tools, not a generic
auto-fix engine or a substitute for domain review:

```bash
uv run anvil fix runs/latest \
  --prompt examples/support_agent/system_prompt.md \
  --tools examples/support_agent/tools.py \
  --out patches/anvil-fix.patch
uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out scenarios/learned_refund_regression.yaml
```

Run an MCP tool-safety audit:

```bash
uv run anvil mcp harden \
  --command-json '["python", "my_mcp_server.py"]' \
  --snapshot-out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --audit-report reports/mcp-audit.md \
  --repair-out reports/mcp-repair.md \
  --offline \
  --github-summary
```

`anvil run` exits with code `1` when any trial fails, so it can fail CI on agent
regressions. For more commands, see the [CLI reference](docs/cli.md). For
scenario syntax, see the [scenario authoring guide](docs/scenarios.md).

## GitHub Actions

This repo runs Agent Anvil against itself in GitHub Actions. The separate
`Agent Anvil` workflow uploads `agent-anvil-runs` with `report.md`,
`results.json`, traces, and `repair_plan.md`. It also writes an Agent Anvil
summary directly into the GitHub Actions run page.

```yaml
- uses: actions/checkout@v6
- uses: agent-axiom/agent-anvil-action@v1.0.0
  with:
    scenario: scenarios/external_jsonl_agent.yaml
    offline: "true"
```

Intentional regression demos can assert the expected failing exit code:

```yaml
- uses: agent-axiom/agent-anvil-action@v1.0.0
  with:
    scenario: scenarios/refund_agent.yaml
    offline: "true"
    agent-mode: offline
    trials: "1"
    expected-exit-code: "1"
    pr-comment: "true"
    post-pr-comment: "true"
```

The action writes `agent-anvil-pr-comment.md` when `pr-comment: "true"`. In
`pull_request` workflows with `pull-requests: write`, `post-pr-comment: "true"`
publishes the same summary directly to the PR.
See the copy-paste [PR comment workflow](docs/examples/pr-comment-workflow.yml).
For MCP servers, see the copy-paste
[MCP safety audit workflow](docs/examples/mcp-harden-workflow.yml), which
snapshots a stdio MCP server, runs static tool-description checks, generates
draft safety scenarios, writes an audit report, and uploads repair hints as
GitHub Actions artifacts.

## Leaderboard Submissions

Agent Anvil can export a small public leaderboard submission from a benchmark
run. The file includes aggregate metrics, evaluator ablation, benchmark hashes,
artifact hashes, and a trust label (`self_reported` or `github_actions`) without
publishing raw traces or tool outputs.

```bash
uv run anvil paper reproduce
uv run anvil leaderboard export docs/paper/results.json \
  --manifest experiments/paper.yaml \
  --agent-name "My Agent" \
  --repo-url "https://github.com/acme/my-agent"
uv run anvil leaderboard validate leaderboard_submission.json
uv run anvil leaderboard build submissions --out leaderboard.csv --json-out leaderboard.json
```

See the [leaderboard submission guide](docs/leaderboard.md) for the Hugging Face
Dataset + Space design. The live public submissions repository is
[agent-axiom/agent-anvil-leaderboard](https://github.com/agent-axiom/agent-anvil-leaderboard),
with the rendered leaderboard on
[Hugging Face Spaces](https://huggingface.co/spaces/ifif/agent-anvil-leaderboard).

## Why AI Was Necessary

Tool-call regressions are workflow failures, not just text-output mismatches.
Agent Anvil uses deterministic checks for exact invariants and OpenAI structured
grading for semantic criteria such as clarification behavior, invalid tool
ordering, instruction violations, and repair suggestions.

## Data Privacy

OpenAI semantic grading redacts email addresses, phone numbers, order IDs,
customer IDs, API keys, bearer tokens, JWTs, and common secret-like values from
scenario and trace payloads by default. Add project-specific semicolon-separated
regexes with `ANVIL_REDACT_PATTERNS`. Use `--no-redact` or `ANVIL_REDACT=false`
only when debugging exact grader payloads. Local run artifacts keep raw traces,
so review them before sharing outside your team.

## More

- [Engineering details](docs/engineering.md)
- [Limits and experimental helpers](docs/limits.md)
- [OpenAI function calling docs](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
