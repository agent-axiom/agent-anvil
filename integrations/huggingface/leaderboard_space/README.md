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
