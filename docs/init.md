# Anvil Init

`anvil init` bootstraps Agent Anvil in an existing agent repository. It writes a
starter external-agent scenario and a GitHub Actions workflow that runs the
scenario in CI.

```bash
uv run anvil init --agent-command "python my_agent.py"
```

For the fastest CI-safe scaffold, use the built-in profile:

```bash
uv run anvil init --profile ci-safe
```

The `ci-safe` profile creates the default `http-python` adapter, writes the
`tool-safety` scenario pack, and enables PR comments in the generated workflow.
Edit the generated adapter and scenario pack before treating the eval result as
your agent's safety signal.
Run `doctor` to check local wiring before opening a PR:

```bash
uv run anvil doctor scenarios/agent_anvil_starter.yaml
```

You can still choose a different JSONL target:

```bash
uv run anvil init --profile ci-safe --agent-command "python my_agent.py"
uv run anvil init --profile ci-safe --adapter openai-agents
```

If you do not have an adapter yet, generate one and wire it into the starter
scenario in one command:

```bash
uv run anvil init --adapter http-python
```

This writes:

- `adapters/http_python_adapter.py`
- `scenarios/agent_anvil_starter.yaml`
- `.github/workflows/agent-anvil.yml`

Use `--adapter-out` to choose a custom adapter path:

```bash
uv run anvil init \
  --adapter openai-agents \
  --adapter-out adapters/openai_agents_adapter.py
```

For an already-running HTTP endpoint agent:

```bash
uv run anvil init \
  --agent-url "http://127.0.0.1:8080/anvil" \
  --header "Authorization=Bearer $ANVIL_AGENT_TOKEN"
```

Generated files:

- `scenarios/agent_anvil_starter.yaml`
- `.github/workflows/agent-anvil.yml`

The starter scenario uses the external JSONL protocol, so your agent receives a
scenario payload on stdin and writes trace events on stdout. Edit the generated
scenario to replace the placeholder input and risky tool name with your own
business invariant.

When using `--agent-url`, the starter scenario uses `protocol: http`, stores the
endpoint URL and headers under `agent:`, and the generated GitHub Actions
workflow runs HTTP conformance before the eval. If your URL is localhost, add a
workflow step that starts your HTTP agent server before the conformance step.
Header values such as `$ANVIL_AGENT_TOKEN` are mapped to same-named GitHub
Secrets in the generated workflow.

The HTTP onboarding flow is:

```bash
uv run anvil init --agent-url "http://127.0.0.1:8080/anvil"
uv run anvil conformance external-agent --url "http://127.0.0.1:8080/anvil"
uv run anvil run scenarios/agent_anvil_starter.yaml --offline
```

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

`anvil init` refuses to overwrite existing files, including generated adapter
files:

```bash
uv run anvil init --agent-command "python my_agent.py"
```

Use `--force` only when you intentionally want to replace the generated scenario
and workflow:

```bash
uv run anvil init --agent-command "python my_agent.py" --force
```
