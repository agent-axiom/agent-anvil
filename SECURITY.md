# Security Policy

Agent Anvil is a local, CI-first evaluation harness. It can execute user-provided
agent commands, read scenario files, write trace artifacts, and optionally send
redacted grader payloads to OpenAI. Treat it as developer tooling with access to
the same files, secrets, and network permissions as the process running it.

## Supported Versions

Agent Anvil is pre-1.0 software. Security fixes target the latest published
release and `main`.

| Version | Security support |
| --- | --- |
| latest `0.2.x` | Supported |
| older `0.2.x` | Best-effort only |
| `0.1.x` and earlier | Unsupported |

If a security fix requires a breaking change before `1.0`, the release notes
will call that out explicitly.

## Reporting a Vulnerability

Report suspected vulnerabilities privately by opening a GitHub Security Advisory
draft or by contacting the maintainers through the repository owner profile.

Include:

- affected version or commit SHA;
- operating system and Python version;
- minimal reproduction steps;
- whether the issue involves local artifacts, external agent commands, OpenAI
  grader payloads, GitHub Actions, or leaderboard submissions;
- any suggested mitigation.

Do not publish secrets, API keys, raw traces with private data, customer data,
or exploit details in public issues or pull requests.

## Security Boundaries

Agent Anvil does not sandbox arbitrary code. These inputs are trusted at the
same level as the repository where you run them:

- scenario files;
- external JSONL agent commands;
- MCP server commands used for audit snapshots;
- shell workflows that call `anvil`;
- custom redaction regexes.

Use a sandboxed CI job or container when evaluating untrusted agents. Do not run
unknown external agent commands on a developer laptop with production secrets.

## Data Handling

OpenAI semantic grading redacts common sensitive values before sending grader
payloads, but local run artifacts keep raw traces. Review `runs/`, reports,
leaderboard submissions, and GitHub Actions artifacts before sharing them.

See [Data Privacy](docs/privacy.md) for the full data-flow contract.

## Dependency Security

Agent Anvil keeps runtime dependencies intentionally small. When reporting a
dependency vulnerability, include whether the vulnerable code path is reachable
from:

- local CLI commands;
- GitHub Action usage;
- OpenAI semantic grading;
- external agent command execution;
- MCP audit commands.

## Disclosure Policy

Maintainers will acknowledge credible reports, investigate impact, and publish a
release note once a fix is available. If a mitigation exists before a release,
the advisory or issue response should describe it without exposing exploit
details.
