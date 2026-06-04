# HTTP Init Onboarding v1

## Goal

Make bring-your-own HTTP endpoint agents easy to bootstrap from a clean
repository without hand-writing scenario YAML or GitHub Actions.

## Scope

- Add `anvil init --agent-url`.
- Add repeatable `--header KEY=VALUE` for generated HTTP scenario headers.
- Generate `agent.protocol: http` starter scenarios.
- Generate GitHub Actions workflows that run HTTP conformance before `anvil run`.
- Map `$ENV_VAR` references in generated headers to same-named GitHub Secrets in
  the workflow environment.
- Keep built-in scenario packs JSONL-command only for this iteration.

## Verification

- CLI tests for generated HTTP scenario and workflow content.
- CLI tests for ambiguous target validation and invalid header usage.
- Documentation tests for README and init guide examples.
- Full ruff, ty, and pytest coverage gate before merge.
