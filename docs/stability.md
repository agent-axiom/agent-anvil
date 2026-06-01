# Stability and Compatibility

Agent Anvil is pre-1.0 software with a stable core and experimental helpers.
The project optimizes for trustworthy CI behavior over broad platform surface.

## Semantic Versioning

Before `1.0`, minor versions may add or refine CLI behavior, schemas, and docs.
Patch versions should be compatible bugfixes, documentation updates, or release
metadata updates.

After `1.0`, Agent Anvil intends to follow semantic versioning:

- patch: compatible fixes and docs;
- minor: backward-compatible features;
- major: breaking changes.

## Stable Core Contract

The stable core should avoid silent behavioral changes:

- `anvil run` exits non-zero when any trial fails;
- deterministic assertions are evaluated before semantic grading;
- `--offline` avoids OpenAI calls;
- traces and results are persisted under the selected runs directory;
- external JSONL protocol errors become failed trace artifacts instead of
  unhandled crashes where possible;
- GitHub Action `expected-exit-code` must match the actual CLI exit code.

## Experimental Helpers

These commands can evolve faster:

- `anvil fix`
- `anvil learn`
- `anvil fuzz`
- `anvil mcp audit`
- `anvil mcp harden`

They are scaffolding helpers. Their output should be reviewed by a human before
being used as policy, prompt, or code.

## Deprecation Policy

Deprecations should:

- be documented in release notes;
- keep the old behavior working for at least one minor release when practical;
- include the replacement command, field, or workflow;
- avoid silent changes to CI exit-code behavior.

Pre-1.0 breaking changes may happen, but they should be explicit and tied to
trust, correctness, or maintainability.

## Supported Runtime

The supported Python floor is declared in `pyproject.toml`. CI currently tests
Python 3.12 and 3.14. The GitHub Action defaults to Python 3.12.

## Compatibility Testing

Compatibility is guarded by:

- pytest with coverage threshold;
- ruff formatting and linting;
- ty type checks;
- doc tests for public examples and version pins;
- self-eval through the Agent Anvil workflow.
