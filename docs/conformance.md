# External Agent Conformance

Use conformance before adding a bring-your-own agent to a scenario suite. It
checks the JSONL protocol contract without running a full benchmark or OpenAI
grading.

```bash
uv run anvil conformance external-agent \
  --agent-command "python my_agent.py" \
  --out reports/external-agent-conformance.md
```

Sample output: [External agent conformance report](conformance-report.md).

If you use a common framework, generate a starter adapter first:

```bash
uv run anvil adapter add openai-agents --out adapters/openai_agents_adapter.py
uv run anvil adapter add langgraph --out adapters/langgraph_adapter.py
```

See [External Agent Adapters](adapters.md).

The command sends the same stdin payload shape used by `anvil run`, parses JSONL
events from stdout, and returns:

- exit code `0` when the external agent is protocol-compatible;
- exit code `1` when the agent emits malformed JSONL, misses `final_output`,
  exceeds `--max-steps`, times out, or exits unsuccessfully;
- exit code `2` for invalid conformance command options.

## Checks

`anvil conformance external-agent` currently verifies:

- the external process produced a completed trace;
- no `agent_protocol_error` event was recorded;
- the trace event count is within `--max-steps`;
- a `final_output` event was emitted.

This is a contract check, not an eval. Passing conformance means Agent Anvil can
consume your agent traces. It does not mean the agent is safe, correct, or ready
for production.

## cwd And env

Use `--cwd` and repeatable `--env KEY=VALUE` when the agent needs a specific
working directory or test configuration.

```bash
uv run anvil conformance external-agent \
  --agent-command "python agent.py" \
  --cwd examples/my_agent \
  --env AGENT_MODE=test \
  --env FEATURE_FLAG_SAFE_TOOLS=true
```

## Fixture Agents

The repository includes small fixtures that demonstrate pass/fail behavior:

```bash
uv run anvil conformance external-agent \
  --agent-command "python fixtures/conformance/pass_agent.py"

uv run anvil conformance external-agent \
  --agent-command "python fixtures/conformance/malformed_agent.py"
```

Use these fixtures as the smallest copy-paste examples for the external JSONL
protocol.
