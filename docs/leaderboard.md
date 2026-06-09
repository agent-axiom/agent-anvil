# Leaderboard Submissions

Agent Anvil leaderboard submissions are designed to be easy to generate and
hard to misrepresent accidentally.

Live submissions repository:
[agent-axiom/agent-anvil-leaderboard](https://github.com/agent-axiom/agent-anvil-leaderboard).

Live Hugging Face leaderboard:
[Space](https://huggingface.co/spaces/ifif/agent-anvil-leaderboard) and
[Dataset](https://huggingface.co/datasets/ifif/agent-anvil-leaderboard-data).
The live submissions repository publishes the rebuilt index to Hugging Face
automatically after merges to `main`.

The user runs Agent Anvil locally or in CI. Agent Anvil exports a small
`leaderboard_submission.json` file with aggregate metrics, evaluator ablation
results, benchmark/scenario hashes, and artifact hashes. It does not include raw
traces, model outputs, tool results, secrets, or PII-bearing scenario content.

## Export A Submission

Reproduce the paper benchmark:

```bash
uv run anvil paper reproduce
```

Export a leaderboard submission:

```bash
uv run anvil leaderboard export docs/paper/results.json \
  --manifest experiments/paper.yaml \
  --out leaderboard_submission.json \
  --agent-name "My Agent" \
  --agent-version "2026-05-22" \
  --repo-url "https://github.com/acme/my-agent" \
  --commit-sha "$(git rev-parse HEAD)"
```

Validate it before publishing:

```bash
uv run anvil leaderboard validate leaderboard_submission.json
```

Inspect the submission as a human reviewer:

```bash
uv run anvil leaderboard inspect leaderboard_submission.json \
  --out leaderboard_inspection.md
```

Generate an independent reproduction script for a maintainer rerun:

```bash
uv run anvil leaderboard reproduce leaderboard_submission.json \
  --out reproduce_leaderboard_submission.sh
```

Prepare a local pull-request file for the public submissions repository:

```bash
uv run anvil leaderboard pr leaderboard_submission.json \
  --leaderboard-repo ../agent-anvil-leaderboard \
  --pr-body-out agent-anvil-leaderboard-pr.md
```

Build a public leaderboard index from accepted submissions:

```bash
uv run anvil leaderboard build submissions \
  --out leaderboard.csv \
  --json-out leaderboard.json \
  --no-artifacts
```

The JSON contains:

- `schema_version`: stable submission schema identifier
- `submitter`: agent name, version, repository, commit, and notes
- `benchmark`: benchmark name plus SHA-256 hashes for the manifest and scenario files
- `metrics`: aggregate pass rates, confidence intervals, missed failures, and outcomes
- `evaluator_ablation`: final-answer, trace-completion, assertion, policy, and full evaluator rates
- `artifacts`: SHA-256 hashes for result and table files
- `verification`: trust level, evidence hash, generator version, and CI run URL when available

## Trust Levels

`self_reported` means the submission was generated outside a recognized CI
environment. It is useful for exploration and community sharing, but a
leaderboard should label it as self-reported.

`github_actions` means the submission was generated in GitHub Actions and
contains `verification.github_run_url`, `verification.github_repository`, and
`verification.github_sha` assembled from GitHub environment variables. The live
Agent Anvil validator rejects `github_actions` rows that omit those fields or
whose run URL does not point at the declared repository. It also requires the
submitted `submitter.commit_sha` to match `verification.github_sha`, so the
public CI evidence and reproduction target refer to the same source revision. The live
leaderboard repository verifies that the run exists, completed successfully, and
matches the submitted repository/SHA through the GitHub API. This is not
cryptographic proof that the agent is honest, but it gives reviewers a public
run to inspect and is the minimum bar for a verified public leaderboard row.

Public benchmark leaderboards should not pretend to prevent all gaming. The
benchmark is visible, so leaderboard rows should be explicit about whether they
are self-reported, CI-verified, or independently re-run by maintainers.

Direct user submissions may only claim `self_reported` or `github_actions`.
`maintainer_rerun` is reserved for maintainer-side rerun attestations, not for
edited submission JSON.

A maintainer rerun attestation is a separate JSON document stored outside the
user submissions directory. Agent Anvil overlays it onto the matching row only
when `original_evidence_sha256`, headline metrics, agent name, benchmark name,
and GitHub Actions rerun URL are valid:

```json
{
  "schema_version": "agent-anvil.leaderboard.maintainer_rerun.v1",
  "status": "verified",
  "original_evidence_sha256": "...",
  "rerun_evidence_sha256": "...",
  "agent_name": "Support Agent",
  "benchmark_name": "paper_benchmark",
  "total_trials": 6,
  "final_answer_pass_rate": 100.0,
  "trace_aware_pass_rate": 100.0,
  "github_run_url": "https://github.com/OWNER/REPO/actions/runs/123456",
  "github_repository": "OWNER/REPO",
  "github_sha": "...",
  "generated_at": "2026-06-09T00:00:00Z",
  "generated_by": "agent-anvil/0.2.65"
}
```

Generate this document from the accepted submission and a maintainer rerun
submission:

```bash
uv run anvil leaderboard attest-rerun \
  submissions/support-agent.json \
  reruns/support-agent.json \
  --out maintainer_reruns/support-agent.json \
  --github-run-url https://github.com/OWNER/REPO/actions/runs/123456

uv run anvil leaderboard validate-rerun \
  submissions/support-agent.json \
  maintainer_reruns/support-agent.json \
  --github-run
```

## Recommended Submission Flow

1. The user runs the benchmark in their own repository or CI.
2. The user exports `leaderboard_submission.json`.
3. The user validates the file locally with `anvil leaderboard validate`.
4. The user or maintainer runs `anvil leaderboard inspect` to review trust
   evidence, benchmark hashes, artifact status, warnings, and the
   reproducibility checklist.
5. A maintainer can run `anvil leaderboard verify-run` to check one submitted
   `github_actions` row against the public GitHub Actions run API without
   requiring local result artifacts.
6. A maintainer can run `anvil leaderboard reproduce` to generate a shell script
   that clones the submitted repository at the claimed commit, reruns the
   benchmark, exports a new submission, and compares the evidence hash plus
   headline metrics. The script is intentionally review-first and must be run in
   a sandbox because it executes submitted code.
7. The user opens a pull request to the leaderboard submissions repository.
8. The leaderboard CI runs
   `anvil leaderboard validate --no-artifacts --github-run` for schema,
   evidence-hash, and GitHub Actions run checks before labeling the row by
   `verification.trust_level`.
9. The leaderboard CI runs
   `anvil leaderboard build submissions --maintainer-reruns maintainer_reruns`
   to regenerate `leaderboard.csv` and `leaderboard.json`.
10. Maintainers can optionally re-run the agent and mark the row as
   `maintainer_rerun` by adding a separate `maintainer_reruns/*.json`
   attestation generated by `anvil leaderboard attest-rerun`. The attestation
   must match the original row evidence hash and point to a successful public
   GitHub Actions rerun.
11. Maintainers can run `anvil leaderboard validate-rerun --github-run` to
   validate one attestation explicitly before regenerating the public index.

Rows upgraded through `--maintainer-reruns` keep the original submission
`evidence_sha256` and add explicit rerun evidence fields to the generated
leaderboard index:

- `maintainer_rerun_url`: public maintainer-side GitHub Actions rerun URL
- `maintainer_rerun_path`: local attestation path used to upgrade the row
- `maintainer_rerun_evidence_sha256`: evidence hash from the maintainer rerun
- `maintainer_rerun_github_repository` and `maintainer_rerun_github_sha`:
  repository/SHA validated for the maintainer rerun

For stricter public rows, generate the submission in GitHub Actions. Producer
workflows should validate structural trust metadata while the run is still in
progress:

```bash
uv run anvil leaderboard validate leaderboard_submission.json \
  --require-trust github_actions
```

Public leaderboard or maintainer CI should add `--github-run` after the
producer run has completed. When `--maintainer-reruns` is also supplied,
`--github-run` verifies maintainer rerun attestation URLs, status, conclusion,
repository, and SHA metadata too:

```bash
uv run anvil leaderboard validate leaderboard_submission.json \
  --require-trust github_actions \
  --github-run
uv run anvil leaderboard verify-run leaderboard_submission.json \
  --out github_run_verification.json
uv run anvil leaderboard verify-all submissions \
  --out github-run-verifications
uv run anvil leaderboard audit submissions \
  --json-out leaderboard_audit.json \
  --markdown-out leaderboard_audit.md \
  --fail-on reject \
  --github-run
```

Use `--json` when another CI step should consume the verification directly from
stdout. The JSON report uses
`agent-anvil.leaderboard.github_run_verification.v1` and includes the submitted
repository, SHA, GitHub run URL, evidence hash, benchmark name, and verifier
version.
Use `verify-all` in leaderboard maintainer CI when you want one stored
verification report per submitted row.
Use `audit` when maintainer CI needs a single decision report across all rows:
`accept` for rows with passing provenance checks, `review` for self-reported or
insufficiently verified rows, and `reject` for invalid, tampered, duplicate, or
failed-provenance rows. Use `--fail-on reject` for public leaderboards that
allow review rows but must block rejected rows.

A copy-paste workflow is available at
[`docs/examples/leaderboard-submission-workflow.yml`](examples/leaderboard-submission-workflow.yml).
It exports a `github_actions` submission, validates that trust level inside the
same GitHub Actions run, stages the JSON under `submission/`, and writes the
destination pull-request path into the GitHub Step Summary. It also creates a
GitHub artifact attestation for `leaderboard_submission.json`, so reviewers can
verify that the submitted row was produced inside the claimed repository run:

```bash
gh attestation verify leaderboard_submission.json -R OWNER/REPO
```

Attestations complement, but do not replace, Agent Anvil's own submission
validation and artifact hash checks. The leaderboard treats them as provenance
evidence for `github_actions` rows.

A second copy-paste workflow,
[`docs/examples/leaderboard-auto-pr-workflow.yml`](examples/leaderboard-auto-pr-workflow.yml),
adds the final handoff: it checks out the public leaderboard repository, runs
`anvil leaderboard pr leaderboard_submission.json --pr-body-out ...`, and opens a
pull request with `gh pr create`. This requires a repository secret named
`LEADERBOARD_PR_TOKEN` with permission to push a branch and open pull requests
against the leaderboard repository. Do not use this token for model calls or
agent tools; it is only for publishing the already generated aggregate JSON.

A copy-paste validator/index workflow for a submissions repository is available
at [`docs/examples/leaderboard-index-workflow.yml`](examples/leaderboard-index-workflow.yml).

## Verified End-To-End Demo

A public reference repository demonstrates the full flow:
[agent-axiom/agent-anvil-demo-agent](https://github.com/agent-axiom/agent-anvil-demo-agent).

The demo repo runs Agent Anvil in GitHub Actions, exports an attested
`github_actions` leaderboard submission, uploads the JSON artifact, opens the
public leaderboard pull request, and publishes provenance status through the
merged row. The current attested source run is
[26656805979](https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26656805979),
and the auto-submitted leaderboard pull request is
[agent-anvil-leaderboard#18](https://github.com/agent-axiom/agent-anvil-leaderboard/pull/18).

## Live Hugging Face Leaderboard

The live public setup is:

1. The public submissions repository stores accepted
   `leaderboard_submission.json` files and generated `leaderboard.csv` /
   `leaderboard.json` indexes.
2. A Hugging Face Space reads the Hugging Face Dataset index and renders the
   leaderboard with a snapshot summary, trust-level filters, repository/name
   search, freshness/stale badges, benchmark compatibility badges, submission
   health badges, minimum-trial filtering, sortable trace-aware metrics, and
   evidence links.
3. Users submit results by opening a pull request to the dataset repository or
   to an Agent Anvil submissions repository.
4. Validators check schema version, required fields, benchmark/scenario hashes,
   artifact hashes, generated leaderboard row metadata, submission health
   warnings, and whether the claimed CI run URL completed successfully for the
   submitted repository/SHA.
5. Rows are labeled as `self_reported`, `github_actions`, or `maintainer_rerun`.
6. Maintainer rerun attestations are applied as a separate overlay after the
   base index is rebuilt, preserving the original submission provenance.
7. The live submissions repository publishes the rebuilt index and Space files
   to Hugging Face when its `HF_TOKEN` repository secret is configured.

Maintainers can create the overlay JSON with the
**Create Maintainer Rerun Attestation** workflow in the live submissions
repository. The workflow accepts a submission path, evidence hash, maintainer
identity, and successful GitHub Actions rerun metadata, then uploads a
reviewable `maintainer-rerun-attestation` artifact for a pull request.

The Space should display aggregate results only. Raw traces stay with the user
unless they intentionally publish them.

The starter Space app lives in
[`integrations/huggingface/leaderboard_space`](../integrations/huggingface/leaderboard_space).
Set `LEADERBOARD_INDEX_URL` to the raw `leaderboard.json` URL in the Dataset
repository, for example:

```text
https://huggingface.co/datasets/ifif/agent-anvil-leaderboard-data/resolve/main/leaderboard.json
```

Recommended Dataset layout:

```text
submissions/
  acme-support-agent.json
  research-lab-agent.json
leaderboard.csv
leaderboard.json
```

## Why Not Run Agents In The Space?

Running arbitrary agents inside the public Space would require executing
untrusted code, handling secrets, paying for model/API calls, and sandboxing
tool side effects. That is the wrong trust boundary for the first public
leaderboard.

The safer model is:

- execution happens in the user's repository or CI;
- Agent Anvil emits a reproducible, hashed submission artifact;
- the public leaderboard displays and validates submissions.
- the automated pull-request flow does not execute arbitrary user agents in the
  leaderboard repository; it only submits the attested aggregate JSON for review.
