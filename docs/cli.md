# CLI Reference

Use `uv run anvil --help` for the live command list. This page keeps the common
copy-paste commands in one place so the README can stay short.

## Run And Report

```bash
uv run anvil run scenarios/refund_agent.yaml
uv run anvil run scenarios/refund_agent.yaml --trials 5
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline
uv run anvil run scenarios/refund_agent.yaml --agent-mode openai
uv run anvil run scenarios/refund_agent.yaml --no-redact
uv run anvil report runs/latest
uv run anvil summary runs/latest --github
uv run anvil compare runs/baseline runs/latest
```

`anvil run` exits with code `1` when any trial fails, so it can fail CI on agent
regressions.

## Repair And Draft Scenario Helpers

```bash
uv run anvil repair runs/latest
uv run anvil fix runs/latest \
  --prompt examples/support_agent/system_prompt.md \
  --tools examples/support_agent/tools.py \
  --out patches/anvil-fix.patch
uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out scenarios/learned_refund_regression.yaml
```

## Project Bootstrap And Packs

```bash
uv run anvil init --agent-command "python my_agent.py"
uv run anvil init --agent-command "python my_agent.py" \
  --pack tool-safety \
  --risky-tool issue_refund \
  --verification-tool lookup_order
uv run anvil pack list
uv run anvil pack add tool-safety \
  --agent-command "python my_agent.py" \
  --risky-tool issue_refund \
  --verification-tool lookup_order \
  --out scenarios/tool_safety_starter.yaml
```

## External Agent Conformance

```bash
uv run anvil conformance external-agent \
  --agent-command "python my_agent.py" \
  --out reports/external-agent-conformance.md
uv run anvil conformance external-agent \
  --agent-command "python agent.py" \
  --cwd examples/my_agent \
  --env AGENT_MODE=test
```

The conformance command verifies that a bring-your-own external JSONL agent emits
parseable trace events and a `final_output` before you add it to a scenario
suite. See [External Agent Conformance](conformance.md).

## Production Trace Ingest

```bash
uv run anvil ingest jsonl logs/agent_failure.jsonl \
  --scenario-id prod_failure_001 \
  --input "user request" \
  --out runs/imported-prod
uv run anvil learn jsonl logs/agent_failure.jsonl \
  --scenario-id prod_failure_001 \
  --input "user request" \
  --out scenarios/prod_regression.yaml
```

## MCP Tool-Safety Audit

```bash
uv run anvil mcp harden \
  --command-json '["python", "my_mcp_server.py"]' \
  --snapshot-out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --audit-report reports/mcp-audit.md \
  --repair-out reports/mcp-repair.md \
  --offline \
  --github-summary

uv run anvil mcp snapshot \
  --command-json '["python", "my_mcp_server.py"]' \
  --out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
uv run anvil mcp audit docs/fixtures/mcp-tools.json \
  --out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
uv run anvil mcp repair docs/fixtures/mcp-tools.json \
  --out reports/mcp-repair.md \
  --offline
```

## Trace Bridge And Scenario Mutation

```bash
uv run anvil trace export runs/latest --format openai-trace --out traces/openai-trace.json
uv run anvil trace import traces/openai-trace.json --format openai-trace --out runs/imported
uv run anvil fuzz scenarios/refund_agent.yaml \
  --mutations 10 \
  --focus tool_safety \
  --out scenarios/refund_agent_fuzzed.yaml
```

## Stable Contracts

```bash
uv run anvil schema export --out schemas
```

This writes JSON Schema files for trace artifacts, scenario suites, leaderboard
submissions, and leaderboard indexes. See [Stable Contracts](contracts.md).

## PR Comments

```bash
uv run anvil pr-comment runs/latest --out agent-anvil-pr-comment.md
```

## Paper Benchmark And Leaderboard Submissions

```bash
uv run anvil paper reproduce
uv run anvil leaderboard export docs/paper/results.json \
  --manifest experiments/paper.yaml \
  --out leaderboard_submission.json \
  --agent-name "My Agent" \
  --agent-version "2026-05-22" \
  --repo-url "https://github.com/acme/my-agent" \
  --commit-sha "$(git rev-parse HEAD)"
uv run anvil leaderboard validate leaderboard_submission.json
uv run anvil leaderboard validate leaderboard_submission.json \
  --require-trust github_actions
uv run anvil leaderboard inspect leaderboard_submission.json \
  --out leaderboard_inspection.md
uv run anvil leaderboard reproduce leaderboard_submission.json \
  --out reproduce_leaderboard_submission.sh
uv run anvil leaderboard pr leaderboard_submission.json \
  --leaderboard-repo ../agent-anvil-leaderboard \
  --pr-body-out agent-anvil-leaderboard-pr.md
uv run anvil leaderboard build submissions \
  --out leaderboard.csv \
  --json-out leaderboard.json \
  --no-artifacts
```

Use `--no-artifacts` on `leaderboard validate` when validating a submitted JSON
row in a repository that does not also contain the referenced result artifacts.
`leaderboard inspect` renders a reviewable trust report with benchmark hashes,
artifact status, warnings, and a reproducibility checklist for maintainers or
community reviewers.
`leaderboard reproduce` writes a reviewable shell script that clones the
submitted repository at the claimed commit, reruns the benchmark, exports a new
submission, and compares the evidence hash plus headline metrics. Review the
script before executing it because it runs the submitted agent repository.
`leaderboard pr` validates the compact submission, writes it under
`submissions/<agent-name>.json` in a local checkout of the public submissions
repository, can write a review-ready PR body with provenance evidence, and
prints the git commands needed to open a reviewable PR.
`leaderboard build` validates all `*.json` submissions, rejects duplicate
evidence hashes, ranks rows per benchmark, and writes CSV/JSON files suitable
for a Hugging Face Dataset-backed public leaderboard.
