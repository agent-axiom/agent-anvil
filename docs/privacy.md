# Data Privacy

Agent Anvil is local-first. It writes run artifacts to your repository checkout
or configured `runs` directory and only sends data to external services when you
choose workflows that do so.

## Default Local Artifacts

Local run artifacts keep raw traces:

- `runs/<run_id>/results.json`
- `runs/<run_id>/report.md`
- `runs/<run_id>/repair_plan.md`
- `runs/<run_id>/traces/*.json`

Local run artifacts keep raw traces so developers can debug exact tool calls and
agent outputs. Review these files before attaching them to GitHub issues, PRs,
leaderboard submissions, bug reports, or chat threads.

## OpenAI Semantic Grading

OpenAI semantic grading is optional. Use `--offline` when you do not want to
call OpenAI.

When OpenAI grading is enabled, Agent Anvil builds a grader payload from the
scenario, expected behavior, trace, and final output. Redaction is enabled by
default and masks common sensitive values before the payload is sent.

The default redactor covers:

- email addresses;
- phone numbers;
- order IDs and customer IDs used by the demo scenarios;
- API keys and common secret-like values;
- bearer tokens;
- JWT-shaped tokens.

Add project-specific semicolon-separated regexes with:

```bash
export ANVIL_REDACT_PATTERNS='tenant_[a-z0-9]+;internal-[0-9]+'
```

Disable redaction only for local debugging:

```bash
uv run anvil run scenarios/refund_agent.yaml --no-redact
```

or:

```bash
export ANVIL_REDACT=false
```

## External Agents

The external JSONL protocol can execute commands such as:

```yaml
agent:
  command: "uv run python my_agent.py"
  protocol: jsonl
  cwd: "."
  env:
    AGENT_MODE: test
```

Those commands run with the permissions of the current process. Do not execute
untrusted agents outside a sandboxed environment. Treat stdout JSONL events and
tool results as potentially sensitive until reviewed.

## GitHub Actions

The GitHub Action uploads only the artifacts configured by the workflow. If you
upload `runs/`, you may upload raw traces. Use private repositories or restricted
artifact retention for sensitive evals.

## Leaderboard Submissions

Leaderboard submissions are aggregate JSON files. They include metrics,
benchmark hashes, artifact hashes, trust metadata, and repository metadata. They
do not include raw traces, model outputs, tool results, secrets, or scenario
content with private data.

Before publishing a submission:

```bash
uv run anvil leaderboard inspect leaderboard_submission.json \
  --out leaderboard_inspection.md
```

## Sharing Checklist

Before sharing Agent Anvil output, check:

- no raw traces with private user data;
- no tool results containing customer, tenant, or internal system data;
- no API keys, bearer tokens, JWTs, or session cookies;
- no private repository paths that matter to your organization;
- no unreviewed generated repair patches.
