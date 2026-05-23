---
title: Agent Anvil Leaderboard
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---

# Agent Anvil Leaderboard Space

This is a minimal Hugging Face Space scaffold for a public Agent Anvil
leaderboard.

It does not execute user agents. It reads a generated `leaderboard.json` file
from a Hugging Face Dataset repository or from the local Space filesystem and
renders aggregate benchmark rows.

## Configure

Set this Space secret or variable:

```text
LEADERBOARD_INDEX_URL=https://huggingface.co/datasets/ifif/agent-anvil-leaderboard-data/resolve/main/leaderboard.json
```

The Dataset repository should be updated by CI with:

```bash
uv run anvil leaderboard build submissions \
  --out leaderboard.csv \
  --json-out leaderboard.json \
  --no-artifacts
```

## Trust Model

Rows are labeled by trust level:

- `self_reported`: generated outside recognized CI
- `github_actions`: generated in GitHub Actions with a public run URL
- `maintainer_rerun`: independently reproduced by maintainers

Maintainer rerun metadata is displayed from the public leaderboard index when a
row has a verified `maintainer_reruns/*.json` attestation.

The Space displays these labels instead of pretending that a public benchmark
cannot be gamed.

## Submit your agent

Run Agent Anvil in your own repository, export a compact submission, and open a
pull request to the public submissions repo:

```bash
uv run anvil paper reproduce
uv run anvil leaderboard export docs/paper/results.json \
  --manifest experiments/paper.yaml \
  --out leaderboard_submission.json \
  --agent-name "My Agent"
uv run anvil leaderboard pr leaderboard_submission.json \
  --leaderboard-repo ../agent-anvil-leaderboard
```

For a `github_actions` row, copy the workflow from
`agent-axiom/agent-anvil-leaderboard` and run it from the Actions tab.

Verified reference:

- Demo repo: https://github.com/agent-axiom/agent-anvil-demo-agent
- Successful GitHub Actions run:
  https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26335581868
- Accepted leaderboard PR:
  https://github.com/agent-axiom/agent-anvil-leaderboard/pull/1
