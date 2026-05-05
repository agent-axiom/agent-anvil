# MCP Tool Audit

Agent Anvil can statically audit exported MCP tool schemas before those tools
are handed to an agent.

Snapshot a live stdio MCP server and audit the captured tool schemas:

```bash
uv run anvil mcp snapshot \
  --command-json '["python", "my_mcp_server.py"]' \
  --out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
```

`--command-json` is recommended because it passes an argv array directly to the
local process. `--command` is still available as a shell-like convenience and is
parsed with `shlex`.

Or audit an existing exported tool schema file:

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

`mcp snapshot` starts the configured stdio command, sends `initialize` and
`tools/list`, saves the returned tool list plus capture metadata, and then exits
the process.

## Security

MCP snapshot commands execute local processes. Treat them like other executable
commands: run only servers you trust, prefer `--command-json` for exact argv
handling, and use a sandbox or container when inspecting third-party MCP
servers.
