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

Current `v0.2.16` also closes the improvement loop:

- `anvil learn`: bad trace -> permanent regression scenario
- `anvil fix`: repair plan -> reviewable prompt/tool patch diff
- `policies`: deterministic guardrails for destructive tools
- `anvil mcp audit`: MCP tool schema audit -> safety scenarios
- `anvil fuzz`: tool-use robustness mutations
- `anvil pr-comment`: PR-ready regression summary
- GitHub Action with Markdown/JSON/trace artifacts

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
