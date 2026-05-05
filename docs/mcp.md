# MCP Tool Audit

Agent Anvil can statically audit exported MCP tool schemas before those tools
are handed to an agent.

```bash
uv run anvil mcp audit docs/fixtures/mcp-tools.json \
  --out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
```

The MVP reads JSON or YAML shaped as either:

```json
[
  {
    "name": "delete_project",
    "description": "Deletes a project.",
    "input_schema": {
      "type": "object",
      "properties": {
        "project_id": { "type": "string" }
      }
    }
  }
]
```

or:

```json
{
  "tools": [
    {
      "name": "delete_project",
      "description": "Deletes a project.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "project_id": { "type": "string" }
        }
      }
    }
  ]
}
```

It flags:

- destructive-looking tool names such as `delete_*`, `transfer_*`, `charge_*`,
  `restart_*`, and `scale_*`
- missing verification or approval language in risky tool descriptions
- arguments without descriptions

The generated scenario suite includes `policies` so risky tools fail
deterministically when called without approval or verified preconditions.

This is intentionally static for now. It does not start arbitrary MCP servers,
which keeps the audit safe to run in CI and easy to review.
