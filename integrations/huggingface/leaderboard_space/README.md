---
title: Agent Anvil Leaderboard
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---

# Agent Anvil Leaderboard Space

This Hugging Face Space renders the public Agent Anvil leaderboard from the
generated `leaderboard.json` index.

By default it reads the published Agent Anvil leaderboard Dataset:

```text
https://huggingface.co/datasets/ifif/agent-anvil-leaderboard-data/resolve/main/leaderboard.json
```

Override the source with this Space variable:

```text
LEADERBOARD_INDEX_URL=https://raw.githubusercontent.com/agent-axiom/agent-anvil-leaderboard/main/leaderboard.json
```

The app does not execute user agents. It only reads aggregate leaderboard rows
that were validated by this repository's GitHub Actions workflow.

The Space includes a snapshot summary, trust-level filters, freshness/stale
badges, benchmark compatibility badges, submission health badges,
repository/name search, minimum-trial filtering, and sortable trace-aware
metrics so users can quickly separate self-reported rows from GitHub Actions
and maintainer-verified results.

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

For a `github_actions` row, copy
`examples/github-actions-submission.yml` into your repository and run it from
the Actions tab.

Trust labels shown by the Space:

- `self_reported`: generated outside recognized CI
- `github_actions`: generated in GitHub Actions with a public run URL
- `maintainer_rerun`: independently reproduced by maintainers

Verified reference:

- Demo repo: https://github.com/agent-axiom/agent-anvil-demo-agent
- Successful GitHub Actions run:
  https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26336840349
- Accepted leaderboard PR:
  https://github.com/agent-axiom/agent-anvil-leaderboard/pull/5
