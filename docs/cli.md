# CLI Reference

Use `uv run anvil --help` for the live command list. This page keeps the common
copy-paste commands in one place so the README can stay short.

## Run And Report

```bash
uv run anvil validate scenarios/refund_agent.yaml
uv run anvil validate --json scenarios/refund_agent.yaml
uv run anvil validate trace runs/latest/traces/refund_valid_order_trial_1.json
uv run anvil validate --strict trace runs/latest/traces/refund_valid_order_trial_1.json
uv run anvil validate --json results runs/latest
uv run anvil validate run runs/latest
uv run anvil validate --json run runs/latest
uv run anvil validate --strict run runs/latest
uv run anvil validate --require-manifest run runs/latest
uv run anvil run scenarios/refund_agent.yaml
uv run anvil run scenarios/refund_agent.yaml --trials 5
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline
uv run anvil run scenarios/refund_agent.yaml --agent-mode openai
uv run anvil run scenarios/refund_agent.yaml --no-redact
uv run anvil report runs/latest
uv run anvil summary runs/latest --github
uv run anvil compare runs/baseline runs/latest
uv run anvil compare runs/baseline runs/latest --json
uv run anvil compare runs/baseline runs/latest --out runs/latest/compare.json
```

`anvil validate` loads a scenario suite and checks schema, policy, expected-tool,
and assertion consistency without running an agent or writing run artifacts.
It can also validate persisted trace and results artifacts with
`anvil validate trace <trace.json>` and `anvil validate results <run-dir|results.json>`.
Versioned `results.json` validation checks that aggregate trial counts and pass
rate match the underlying per-trial grades.
Use `anvil validate run <run-dir>` to verify `results.json` plus every trace
artifact in a persisted run directory, including that every `results.grades`
entry has a matching `scenario_id` / `trial` trace, every trace belongs to the
same `run_id`, every grade `trace_path` points back to the matching
`traces/*.json` artifact, and there are no orphan or duplicate traces. When
`manifest.json` exists, run validation also verifies the SHA-256 hash and byte
size of every manifested artifact and checks that every canonical run artifact
is covered by the manifest. The JSON and text output include an artifact trust summary
showing whether trace-index, grade trace path, hash, size, and manifest coverage
checks were performed.
Use `--require-manifest` in CI when the run directory must include
tamper-evident artifact hashes.
Trace validation is permissive by default so older/custom observer events can
still be inspected. Use `--strict` in CI when unknown trace event types should
fail the validation contract.
Use `--json` for machine-readable preflight output in CI/editor integrations.

`anvil run` exits with code `1` when any trial fails, so it can fail CI on agent
regressions.

`anvil compare --json` emits pass-rate deltas, new/resolved failures, severity
changes, flaky scenario deltas, scenario regressions, and scenario improvements
as machine-readable JSON for CI bots and PR comments.
Use `anvil compare --out compare.json` to persist the same machine-readable
payload while keeping the terminal output human-readable.

## Repair And Draft Scenario Helpers

```bash
uv run anvil repair runs/latest
uv run anvil fix runs/latest \
  --prompt examples/support_agent/system_prompt.md \
  --tools examples/support_agent/tools.py \
  --out patches/anvil-fix.patch
uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out scenarios/learned_refund_regression.yaml
```

## Project Bootstrap And Packs

```bash
uv run anvil init --profile ci-safe
uv run anvil init --agent-command "python my_agent.py"
uv run anvil init --adapter http-python
uv run anvil init --adapter openai-agents --adapter-out adapters/openai_agents_adapter.py
uv run anvil init --agent-url "http://127.0.0.1:8080/anvil"
uv run anvil init --agent-url "http://127.0.0.1:8080/anvil" \
  --header "Authorization=Bearer $ANVIL_AGENT_TOKEN"
uv run anvil init --agent-command "python my_agent.py" \
  --pack tool-safety \
  --risky-tool issue_refund \
  --verification-tool lookup_order
uv run anvil pack list
uv run anvil pack add tool-safety \
  --agent-command "python my_agent.py" \
  --risky-tool issue_refund \
  --verification-tool lookup_order \
  --out scenarios/tool_safety_starter.yaml
uv run anvil doctor scenarios/agent_anvil_starter.yaml
uv run anvil doctor scenarios/agent_anvil_starter.yaml --skip-conformance
uv run anvil doctor scenarios/agent_anvil_starter.yaml --skip-workflow
uv run anvil doctor scenarios/agent_anvil_starter.yaml --json
uv run anvil doctor scenarios/agent_anvil_starter.yaml --out reports/doctor.json
uv run anvil doctor scenarios/agent_anvil_starter.yaml --github-summary
```

`doctor` checks external-agent conformance plus GitHub Actions wiring: checkout
before Agent Anvil, matching scenario paths, PR comment permissions, and stale
Marketplace action refs such as older `agent-axiom/agent-anvil-action@v1.x.y`
pins.

## External Agent Adapters

```bash
uv run anvil adapter list
uv run anvil adapter add http-python --out adapters/http_python_adapter.py
uv run anvil adapter add openai-agents --out adapters/openai_agents_adapter.py
uv run anvil adapter add langgraph --out adapters/langgraph_adapter.py
uv run anvil adapter add langgraph --out adapters/langgraph_adapter.py --force
```

Adapter templates help bridge common frameworks into the external JSONL
protocol. See [External Agent Adapters](adapters.md).

## External Agent Conformance

```bash
uv run anvil conformance external-agent \
  --agent-command "python my_agent.py" \
  --out reports/external-agent-conformance.md
uv run anvil conformance external-agent \
  --agent-command "python agent.py" \
  --cwd examples/my_agent \
  --env AGENT_MODE=test
uv run anvil conformance external-agent \
  --url "http://127.0.0.1:8080/anvil" \
  --header "Authorization=Bearer $ANVIL_AGENT_TOKEN"
```

The conformance command verifies that a bring-your-own JSONL command agent or
HTTP endpoint agent emits parseable trace events and a `final_output` before you
add it to a scenario suite. See [External Agent Conformance](conformance.md).

HTTP agents are configured in scenario YAML for full eval runs:

```yaml
agent:
  protocol: http
  url: "http://127.0.0.1:8080/anvil"
  headers:
    Authorization: "Bearer $ANVIL_AGENT_TOKEN"
```

## Production Trace Ingest

```bash
uv run anvil ingest jsonl logs/agent_failure.jsonl \
  --scenario-id prod_failure_001 \
  --input "user request" \
  --out runs/imported-prod
uv run anvil learn jsonl logs/agent_failure.jsonl \
  --scenario-id prod_failure_001 \
  --input "user request" \
  --out scenarios/prod_regression.yaml
```

## MCP Tool-Safety Audit

```bash
uv run anvil mcp harden \
  --command-json '["python", "my_mcp_server.py"]' \
  --snapshot-out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --audit-report reports/mcp-audit.md \
  --repair-out reports/mcp-repair.md \
  --offline \
  --github-summary

uv run anvil mcp snapshot \
  --command-json '["python", "my_mcp_server.py"]' \
  --out reports/mcp-tools.json \
  --audit-out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
uv run anvil mcp audit docs/fixtures/mcp-tools.json \
  --out scenarios/mcp_tool_safety.yaml \
  --report reports/mcp-audit.md
uv run anvil mcp repair docs/fixtures/mcp-tools.json \
  --out reports/mcp-repair.md \
  --offline
```

## Trace Bridge And Scenario Mutation

```bash
uv run anvil trace export runs/latest --format openai-trace --out traces/openai-trace.json
uv run anvil trace import traces/openai-trace.json --format openai-trace --out runs/imported
uv run anvil fuzz scenarios/refund_agent.yaml \
  --mutations 10 \
  --focus tool_safety \
  --out scenarios/refund_agent_fuzzed.yaml
```

## Stable Contracts

```bash
uv run anvil schema export --out schemas
```

This writes JSON Schema files for trace artifacts, scenario suites, run results,
compare results, leaderboard submissions, and leaderboard indexes. See
[Stable Contracts](contracts.md).

## PR Comments

```bash
uv run anvil pr-comment runs/latest --out agent-anvil-pr-comment.md
uv run anvil pr-comment runs/latest \
  --compare runs/latest/compare.json \
  --out agent-anvil-pr-comment.md
```

When `--compare` is set, malformed or missing compare artifacts are surfaced in
the generated PR comment instead of being silently ignored.

## Paper Benchmark And Leaderboard Submissions

```bash
uv run anvil paper reproduce
uv run anvil leaderboard export docs/paper/results.json \
  --manifest experiments/paper.yaml \
  --out leaderboard_submission.json \
  --agent-name "My Agent" \
  --agent-version "2026-05-22" \
  --repo-url "https://github.com/acme/my-agent" \
  --commit-sha "$(git rev-parse HEAD)"
uv run anvil leaderboard validate leaderboard_submission.json
uv run anvil leaderboard validate leaderboard_submission.json \
  --require-trust github_actions \
  --github-run
uv run anvil leaderboard verify-run leaderboard_submission.json \
  --out github_run_verification.json
uv run anvil leaderboard verify-run leaderboard_submission.json --json
uv run anvil leaderboard verify-all submissions \
  --out github-run-verifications
uv run anvil leaderboard audit submissions \
  --maintainer-reruns maintainer_reruns \
  --json-out leaderboard_audit.json \
  --markdown-out leaderboard_audit.md \
  --fail-on reject \
  --github-run
uv run anvil leaderboard inspect leaderboard_submission.json \
  --out leaderboard_inspection.md
uv run anvil leaderboard reproduce leaderboard_submission.json \
  --out reproduce_leaderboard_submission.sh
uv run anvil leaderboard validate-rerun \
  submissions/support-agent.json \
  maintainer_reruns/support-agent.json \
  --github-run
uv run anvil leaderboard pr leaderboard_submission.json \
  --leaderboard-repo ../agent-anvil-leaderboard \
  --pr-body-out agent-anvil-leaderboard-pr.md
uv run anvil leaderboard build submissions \
  --out leaderboard.csv \
  --json-out leaderboard.json \
  --no-artifacts \
  --github-run
```

Use `--no-artifacts` on `leaderboard validate` when validating a submitted JSON
row in a repository that does not also contain the referenced result artifacts.
Use `--github-run` in public leaderboard CI to verify that a `github_actions`
row points to a completed successful GitHub Actions run for the submitted
repository/SHA.
`leaderboard verify-run` is the single-submission maintainer check for the same
GitHub Actions trust evidence; it skips local artifact hashes and requires a
`github_actions` row. Add `--json` for machine-readable stdout or `--out` to
persist a signed-off verification artifact in CI.
`leaderboard verify-all` applies the same check to every submitted JSON row in a
directory and writes one machine-readable GitHub-run verification report per
submission.
`leaderboard audit` classifies every row as `accept`, `review`, or `reject` and
writes a JSON plus Markdown maintainer decision report. By default it exits
non-zero on review or reject; use `--fail-on reject` when public leaderboard CI
should allow review rows but fail rejected rows, or `--fail-on never` for
report-only jobs. Add `--maintainer-reruns` to apply maintainer rerun
attestations to the audit report before decisions are summarized.
`leaderboard inspect` renders a reviewable trust report with benchmark hashes,
artifact status, warnings, and a reproducibility checklist for maintainers or
community reviewers.
`leaderboard reproduce` writes a reviewable shell script that clones the
submitted repository at the claimed commit, reruns the benchmark, exports a new
submission, and compares the evidence hash plus headline metrics. Review the
script before executing it because it runs the submitted agent repository.
`leaderboard validate-rerun` checks one maintainer rerun attestation against the
original accepted submission. Add `--github-run` when maintainer CI should also
verify the attestation's public GitHub Actions rerun URL, status, repository,
and SHA.
`leaderboard pr` validates the compact submission, writes it under
`submissions/<agent-name>.json` in a local checkout of the public submissions
repository, can write a review-ready PR body with provenance evidence, and
prints the git commands needed to open a reviewable PR.
`leaderboard build` validates all `*.json` submissions, rejects duplicate
evidence hashes, ranks rows per benchmark, and writes CSV/JSON files suitable
for a Hugging Face Dataset-backed public leaderboard.
