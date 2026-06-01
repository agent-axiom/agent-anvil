# Contributing

Thanks for helping improve Agent Anvil.

## Development

```bash
uv sync --group dev
uv run --group dev ruff format .
uv run --group dev ruff check .
uv run --group dev ty check
uv run --group dev pytest --cov=anvil --cov-fail-under=90
```

Quick smoke test:

```bash
uv run anvil run scenarios/external_jsonl_agent.yaml --offline
```

## Writing Scenarios

Start with one behavior you want to prevent from regressing. Good scenarios are
small, specific, and trace-focused:

- wrong tool called
- risky tool called too early
- invalid or invented tool arguments
- missing clarification
- loop after a tool error
- policy precondition violated

See [Scenario Authoring Guide](docs/scenarios.md).

## Bring Your Own Agent

For agents outside this repo, use the external JSONL protocol:

```yaml
agent:
  command: "uv run python my_agent.py"
  protocol: jsonl
  cwd: "."
  env:
    AGENT_MODE: test
```

See [External JSONL Agent Protocol](docs/protocol.md).

## Data Privacy

OpenAI semantic grading redacts common sensitive values before sending grader
payloads, but local `runs/` artifacts keep raw traces. Review run artifacts
before attaching them to issues or PRs.

If your trace includes project-specific secrets, configure:

```bash
export ANVIL_REDACT_PATTERNS='tenant_[a-z0-9]+;internal-[0-9]+'
```

Use `--offline` for local heuristic grading when you do not want to call OpenAI.

See [Data Privacy](docs/privacy.md), [Trust Center](docs/trust.md), and
[SECURITY.md](SECURITY.md) for the supported security boundaries, privacy
contract, and vulnerability reporting process.

## Pull Requests

Keep PRs narrow and include:

- scenario or trace fixture for the behavior
- deterministic tests where possible
- docs update when user-facing behavior changes
- output from the quality gate above
