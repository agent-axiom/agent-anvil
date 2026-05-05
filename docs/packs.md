# Scenario Packs

Scenario packs are reusable starter eval suites for common tool-use risks. They
help teams start from known safety invariants instead of writing every YAML
scenario from scratch.

List built-in packs:

```bash
uv run anvil pack list
```

Add the tool-safety pack:

```bash
uv run anvil pack add tool-safety \
  --agent-command "python my_agent.py" \
  --risky-tool issue_refund \
  --verification-tool lookup_order \
  --out scenarios/tool_safety_starter.yaml
```

## tool-safety

The `tool-safety` pack targets domain-neutral risky-tool behavior:

- destructive tools called before verification
- hallucinated or unknown identifiers
- proceeding after ambiguous verification or tool errors
- missing approval before high-impact operations

It generates:

- external JSONL agent config
- `destructive_tools` policy entries
- `require_before` policy preconditions
- `require_human_approval` policy entries
- three starter scenarios to customize

Customization flags:

- `--risky-tool`: destructive or high-impact tool to block until verified; repeatable
- `--verification-tool`: lookup or verification tool required before risky tools; repeatable
- `--approval-required-tool`: risky tool that should require human approval; repeatable

You can also use it during project bootstrap:

```bash
uv run anvil init \
  --agent-command "python my_agent.py" \
  --pack tool-safety \
  --risky-tool issue_refund \
  --verification-tool lookup_order
```

Review the generated YAML before committing it. Packs are intentionally
conservative templates; replace placeholder tool names and inputs with your
agent's real business invariants.
