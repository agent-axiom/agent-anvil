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
  --leaderboard-repo ../agent-anvil-leaderboard
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
leaderboard repository verifies that the run exists, completed successfully, and
matches the submitted repository/SHA through the GitHub API. This is not
cryptographic proof that the agent is honest, but it gives reviewers a public
run to inspect and is the minimum bar for a verified public leaderboard row.

Public benchmark leaderboards should not pretend to prevent all gaming. The
benchmark is visible, so leaderboard rows should be explicit about whether they
are self-reported, CI-verified, or independently re-run by maintainers.

## Recommended Submission Flow

1. The user runs the benchmark in their own repository or CI.
2. The user exports `leaderboard_submission.json`.
3. The user validates the file locally with `anvil leaderboard validate`.
4. The user or maintainer runs `anvil leaderboard inspect` to review trust
   evidence, benchmark hashes, artifact status, warnings, and the
   reproducibility checklist.
5. A maintainer can run `anvil leaderboard reproduce` to generate a shell script
   that clones the submitted repository at the claimed commit, reruns the
   benchmark, exports a new submission, and compares the evidence hash plus
   headline metrics. The script is intentionally review-first and must be run in
   a sandbox because it executes submitted code.
6. The user opens a pull request to the leaderboard submissions repository.
7. The leaderboard CI runs `anvil leaderboard validate --no-artifacts` for schema
   and evidence-hash checks, then verifies `github_actions` evidence through the
   GitHub API before labeling the row by `verification.trust_level`.
8. The leaderboard CI runs `anvil leaderboard build submissions` to regenerate
   `leaderboard.csv` and `leaderboard.json`.
9. Maintainers can optionally re-run the agent and mark the row as
   `maintainer_rerun` by adding a separate `maintainer_reruns/*.json`
   attestation. The attestation must match the original row evidence hash and
   point to a successful public GitHub Actions rerun.

For stricter public rows, generate the submission in GitHub Actions and validate
with:

```bash
uv run anvil leaderboard validate leaderboard_submission.json \
  --require-trust github_actions
```

A copy-paste workflow is available at
[`docs/examples/leaderboard-submission-workflow.yml`](examples/leaderboard-submission-workflow.yml).
It exports a `github_actions` submission, validates that trust level inside the
same GitHub Actions run, stages the JSON under `submission/`, and writes the
destination pull-request path into the GitHub Step Summary.

A copy-paste validator/index workflow for a submissions repository is available
at [`docs/examples/leaderboard-index-workflow.yml`](examples/leaderboard-index-workflow.yml).

## Verified End-To-End Demo

A public reference repository demonstrates the full flow:
[agent-axiom/agent-anvil-demo-agent](https://github.com/agent-axiom/agent-anvil-demo-agent).

The demo repo runs Agent Anvil in GitHub Actions, exports a
`github_actions` leaderboard submission, uploads the JSON artifact, and then
submits it to the public leaderboard. The successful source run is
[26336840349](https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26336840349),
and the accepted leaderboard pull request is
[agent-anvil-leaderboard#5](https://github.com/agent-axiom/agent-anvil-leaderboard/pull/5).

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
