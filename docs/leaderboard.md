# Leaderboard Submissions

Agent Anvil leaderboard submissions are designed to be easy to generate and
hard to misrepresent accidentally.

Live submissions repository:
[agent-axiom/agent-anvil-leaderboard](https://github.com/agent-axiom/agent-anvil-leaderboard).

Live Hugging Face leaderboard:
[Space](https://huggingface.co/spaces/ifif/agent-anvil-leaderboard) and
[Dataset](https://huggingface.co/datasets/ifif/agent-anvil-leaderboard-data).

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
contains a workflow run URL assembled from GitHub environment variables. This is
not cryptographic proof that the agent is honest, but it gives reviewers a
public run to inspect and is the minimum bar for a verified public leaderboard
row.

Public benchmark leaderboards should not pretend to prevent all gaming. The
benchmark is visible, so leaderboard rows should be explicit about whether they
are self-reported, CI-verified, or independently re-run by maintainers.

## Recommended Submission Flow

1. The user runs the benchmark in their own repository or CI.
2. The user exports `leaderboard_submission.json`.
3. The user validates the file locally with `anvil leaderboard validate`.
4. The user opens a pull request to the leaderboard submissions repository.
5. The leaderboard CI runs `anvil leaderboard validate --no-artifacts` for schema
   and evidence-hash checks, then labels the row by `verification.trust_level`.
6. The leaderboard CI runs `anvil leaderboard build submissions` to regenerate
   `leaderboard.csv` and `leaderboard.json`.
7. Maintainers can optionally re-run the agent and mark the row as
   `maintainer_rerun`.

For stricter public rows, generate the submission in GitHub Actions and validate
with:

```bash
uv run anvil leaderboard validate leaderboard_submission.json \
  --require-trust github_actions
```

A copy-paste workflow is available at
[`docs/examples/leaderboard-submission-workflow.yml`](examples/leaderboard-submission-workflow.yml).

A copy-paste validator/index workflow for a submissions repository is available
at [`docs/examples/leaderboard-index-workflow.yml`](examples/leaderboard-index-workflow.yml).

## Hugging Face Leaderboard Plan

The recommended public setup is:

1. The public submissions repository stores accepted
   `leaderboard_submission.json` files and generated `leaderboard.csv` /
   `leaderboard.json` indexes. It can be mirrored to a Hugging Face Dataset
   repository if the community wants Hugging Face-native dataset history.
2. A Hugging Face Space reads the dataset/index and renders the leaderboard with
   filters for benchmark version, trust level, agent type, pass rate, missed
   failures, and evidence links.
3. Users submit results by opening a pull request to the dataset repository or
   to an Agent Anvil submissions repository.
4. A validator checks schema version, required fields, benchmark/scenario hashes,
   artifact hashes, and whether the claimed CI run URL exists.
5. Rows are labeled as `self_reported`, `github_actions`, or `maintainer_rerun`.

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
