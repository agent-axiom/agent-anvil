# MCP Tool Audit

Agent Anvil can statically audit exported MCP tool schemas before those tools
are handed to an agent.

Snapshot a live stdio MCP server, generate draft safety scenarios, write a
static audit report, and produce repair hints:

```bash
uv run anvil mcp harden \
  --command-json '["python", "my_mcp_server.py"]' \
  --snapshot-out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --audit-report reports/mcp-audit.md \
  --repair-out reports/mcp-repair.md \
  --offline \
  --github-summary
```

Or snapshot and audit only:

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

`mcp harden` is the copy-paste path for CI demos: it chains `snapshot`, `audit`,
and `repair` so a live MCP server produces all Agent Anvil artifacts in one run.
The checks are static tool-schema heuristics, not a full MCP safety analyzer.
With `--github-summary`, it appends a compact Markdown summary to the GitHub
Actions run page when `GITHUB_STEP_SUMMARY` is available.

Or audit an existing exported tool schema file:

```bash
uv run anvil mcp audit docs/fixtures/mcp-tools.json \
  --out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
uv run anvil mcp repair docs/fixtures/mcp-tools.json \
  --out reports/mcp-repair.md \
  --offline
```

`mcp repair` turns audit findings into tool-description, policy, and scenario
repair hints. Without `--offline`, it uses OpenAI structured outputs to produce
a richer repair plan; with `--offline`, it emits deterministic local hints for
CI-safe demos.

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
