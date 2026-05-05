# Anvil Init

`anvil init` bootstraps Agent Anvil in an existing agent repository. It writes a
starter external-agent scenario and a GitHub Actions workflow that runs the
scenario in CI.

```bash
uv run anvil init --agent-command "python my_agent.py"
```

Generated files:

- `scenarios/agent_anvil_starter.yaml`
- `.github/workflows/agent-anvil.yml`

The starter scenario uses the external JSONL protocol, so your agent receives a
scenario payload on stdin and writes trace events on stdout. Edit the generated
scenario to replace the placeholder input and risky tool name with your own
business invariant.

To start from reusable tool-safety scenarios:

```bash
uv run anvil init \
  --agent-command "python my_agent.py" \
  --pack tool-safety \
  --risky-tool issue_refund \
  --verification-tool lookup_order
```

See [Scenario Packs](packs.md).

## PR Comments

For pull request review comments, generate a workflow with:

```bash
uv run anvil init --agent-command "python my_agent.py" --post-pr-comment
```

This grants `pull-requests: write` and sets `post-pr-comment: "true"` on the
Agent Anvil action. The action then publishes the pass rate, top failure cluster,
repair hint, and first failing trace path directly to the PR.

## Existing Files

`anvil init` refuses to overwrite existing files:

```bash
uv run anvil init --agent-command "python my_agent.py"
```

Use `--force` only when you intentionally want to replace the generated scenario
and workflow:

```bash
uv run anvil init --agent-command "python my_agent.py" --force
```
