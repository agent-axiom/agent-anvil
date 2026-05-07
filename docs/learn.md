# Anvil Learn

`anvil learn` turns a bad agent trace into a draft regression scenario.

```bash
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1 || true
uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out scenarios/learned_refund_regression.yaml
```

Review the generated YAML before committing it with the rest of your scenarios:

```bash
uv run anvil run scenarios/learned_refund_regression.yaml --offline
```

For the MVP, learning is deterministic and local. It detects destructive tool
calls with missing or synthetic arguments, keeps useful supporting tool calls,
adds clarification criteria when identifiers are missing, and records the source
trace in `learned_from`.

This is the intended workflow:

1. an agent fails in CI or production
2. Agent Anvil records the trace
3. `anvil learn` turns that trace into a draft regression scenario
4. the scenario is reviewed and committed
5. future prompt, tool, or guardrail changes must keep that scenario passing

Inputs are redacted before the learned scenario is written. Raw traces remain in
`runs/`, so review them before sharing artifacts outside your team. This command
is a scaffold for regression authoring, not a substitute for domain judgment.
