# Discord Challenge Submission

Agent Anvil — CI-first eval harness for tool-using OpenAI agents.

Most evals ask: "was the final answer good?" Agent Anvil asks: "did the agent
behave safely while getting there?"

It runs YAML scenario suites, records model/tool traces, checks tool choice,
arguments, policy preconditions, clarification behavior, and loops, uses OpenAI
structured semantic grading, clusters failures, and generates concrete
prompt/tool/guardrail repair plans.

The demo catches a refund agent calling `issue_refund(order_id="UNKNOWN")`
before order verification — a workflow bug final-answer evals often miss.

Current `v0.2.38` keeps the core product focused on trace-first CI:

- YAML scenario suites and multi-trial runs
- model/tool trace recording
- deterministic assertions and destructive-tool policies
- OpenAI structured semantic grading
- failure clustering and repair plans
- external JSONL protocol for bring-your-own-agent workflows
- reusable GitHub Action with run artifacts, Step Summary, and PR comments

Public proof path:

- demo agent run:
  https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26656805979
- auto-submitted leaderboard PR:
  https://github.com/agent-axiom/agent-anvil-leaderboard/pull/18
- live Hugging Face leaderboard:
  https://huggingface.co/spaces/ifif/agent-anvil-leaderboard

It also includes experimental workflow helpers:

- `anvil learn`: bad trace -> draft regression scenario for human review
- `anvil fix`: demo repair signal -> reviewable prompt/tool patch diff
- `anvil mcp audit`: MCP tool schema lint -> draft safety scenarios
- `anvil mcp harden`: live MCP server -> snapshot, static audit, repair hints
- `anvil fuzz`: deterministic scenario mutation helper

Repo: https://github.com/agent-axiom/agent-anvil

Try it:

```bash
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1 || true
uv run anvil repair runs/latest
uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out scenarios/learned_refund_regression.yaml
```

Why AI was necessary: Agent Anvil uses OpenAI APIs both as a real tool-calling
demo agent and as a structured semantic trace grader. The system evaluates
workflow behavior that deterministic final-answer checks cannot judge reliably:
wrong tool timing, unsafe arguments, missing clarification, and business-policy
violations.

Short line for reviewers: final-answer evals ask whether the answer looked good;
Agent Anvil asks whether the agent behaved safely while getting there.
