# GitHub Marketplace Notes

Agent Anvil ships as a composite GitHub Action from this repository:

```yaml
- uses: agent-axiom/agent-anvil@v0.2.1
  with:
    scenario: scenarios/external_jsonl_agent.yaml
    offline: "true"
```

The action has Marketplace metadata in `action.yml`:

- `name`: Agent Anvil
- `description`: Run Agent Anvil scenario suites in GitHub Actions.
- `branding.icon`: `activity`
- `branding.color`: `purple`

Before listing it in GitHub Marketplace:

1. Keep README quickstart copy-paste safe.
2. Keep the latest release tag aligned with README examples.
3. Verify `action.yml` is at repository root.
4. Confirm the action works from a tag, not only from `./`.
5. Decide whether to keep the action in this repo or publish a tiny wrapper repo
   later for a cleaner Marketplace surface.

The current repository is already usable as an action by tag. A separate wrapper
repo is optional polish, not a blocker for the challenge submission.
