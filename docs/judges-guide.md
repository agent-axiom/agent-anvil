# Judges Guide

Use this path to evaluate Agent Anvil in about three minutes.

## 1. What to Look For

Agent Anvil is a trace-first CI harness for tool-using agents. It evaluates
whether the agent behaved safely while getting to the answer, not just whether
the final text looked good.

The system includes:

- YAML scenario suites
- multi-trial execution
- model/tool trace recording
- deterministic checks for tool choice, arguments, clarification, loops, and policies
- OpenAI structured semantic grading
- failure clustering
- repair plans and patch suggestions
- learned regression scenarios from traces
- external JSONL agent protocol
- MCP tool hardening
- GitHub Action, PR comments, and Step Summary output

## 2. Run the Fast Demo

```bash
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1 || true
uv run anvil repair runs/latest
uv run anvil summary runs/latest --github
```

This intentionally catches a refund agent calling `issue_refund` before order
verification.

Open:

- `runs/latest/report.md`
- `runs/latest/repair_plan.md`
- `runs/latest/results.json`
- `runs/latest/traces/`

## 3. Check the Improvement Loop

```bash
uv run anvil fix runs/latest \
  --prompt examples/support_agent/system_prompt.md \
  --tools examples/support_agent/tools.py \
  --out patches/anvil-fix.patch

uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out scenarios/learned_refund_regression.yaml
```

This shows the loop: failing trace -> repair plan -> reviewable patch ->
permanent regression scenario.

## 4. Check MCP Tool Hardening

```bash
uv run anvil mcp harden \
  --command-json '["python", "docs/examples/fake_mcp_server.py"]' \
  --snapshot-out reports/mcp/mcp-tools.json \
  --audit-out reports/mcp/mcp_tool_safety.yaml \
  --audit-report reports/mcp/mcp-audit.md \
  --repair-out reports/mcp/mcp-repair.md \
  --offline \
  --github-summary
```

Open:

- `reports/mcp/mcp-tools.json`
- `reports/mcp/mcp_tool_safety.yaml`
- `reports/mcp/mcp-audit.md`
- `reports/mcp/mcp-repair.md`

This shows how Agent Anvil can inspect a live MCP server before agents use its
tools, generate safety evals, and suggest safer tool descriptions.

## 5. Check OpenAI Usage

With `OPENAI_API_KEY` set:

```bash
uv run --env-file .env anvil run scenarios/refund_agent.yaml --agent-mode openai --trials 1
```

OpenAI is used in two ways:

- real tool-calling demo agent through the Responses API
- structured semantic trace grading and repair suggestions

CI demos stay offline by default so contributors do not need API keys.

## 6. CI Evidence

Check GitHub Actions:

- `CI`: pytest, ruff, ty, coverage threshold
- `Agent Anvil`: runs Agent Anvil against itself, uploads run artifacts, runs MCP hardening
- `OpenAI Demo`: manual workflow for real OpenAI runs with repository secrets

The repository also includes copy-paste examples:

- `docs/examples/pr-comment-workflow.yml`
- `docs/examples/mcp-harden-workflow.yml`

## 7. Why This Is a System, Not a Prompt

Agent Anvil persists state and artifacts across a full evaluation pipeline:

```text
scenarios -> runner -> agent -> traces -> deterministic checks
          -> OpenAI semantic grading -> clustering -> repair plans
          -> learned regression scenarios -> CI artifacts
```

That makes it useful for regression prevention, not just one-off prompting.
