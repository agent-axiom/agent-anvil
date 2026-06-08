# GitHub Marketplace Notes

Agent Anvil ships as a dedicated GitHub Marketplace action:

```yaml
- name: Agent Anvil
  uses: agent-axiom/agent-anvil-action@v1.0.37
  with:
    scenario: scenarios/external_jsonl_agent.yaml
    offline: "true"
```

Marketplace repository:

- <https://github.com/agent-axiom/agent-anvil-action>

The wrapper action has Marketplace metadata in its root `action.yml`:

- `name`: Agent Anvil
- `description`: Run Agent Anvil scenario suites in CI and publish trace-first eval artifacts.
- `branding.icon`: `activity`
- `branding.color`: `purple`

Release tags:

- `v1.0.0` for exact pinning
- `v1` for stable major-version workflows

This repository uses the Marketplace action in its own `Agent Anvil` workflow so
the published action is continuously exercised against real project scenarios.

For CI safety audits of MCP servers, use
[`docs/examples/mcp-harden-workflow.yml`](examples/mcp-harden-workflow.yml). It
runs `anvil mcp harden`, appends a GitHub Step Summary, and uploads snapshot,
audit, generated draft scenarios, and repair-hint artifacts.
