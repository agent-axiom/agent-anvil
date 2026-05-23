from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.request import urlopen

gr: Any = import_module("gradio")
pd: Any = import_module("pandas")

INDEX_URL = os.getenv("LEADERBOARD_INDEX_URL", "")
INDEX_PATH = Path(os.getenv("LEADERBOARD_INDEX_PATH", "leaderboard.json"))

TRUST_BADGES = {
    "self_reported": "self-reported",
    "github_actions": "GitHub Actions verified",
    "maintainer_rerun": "maintainer rerun",
}

COLUMNS = [
    "rank",
    "agent_name",
    "agent_version",
    "benchmark_name",
    "trust_level",
    "trust_badge",
    "trace_aware_pass_rate",
    "final_answer_pass_rate",
    "answer_only_missed_failures",
    "answer_only_missed_failure_rate",
    "total_trials",
    "repo_url",
    "commit_sha",
    "github_run_url",
    "maintainer",
    "maintainer_rerun_url",
    "maintainer_rerun_repository",
    "maintainer_rerun_sha",
    "evidence_sha256",
]


def load_rows() -> Any:
    payload = _load_payload()
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    frame = pd.DataFrame(rows)
    for column in COLUMNS:
        if column not in frame:
            frame[column] = ""
    frame["trust_badge"] = frame["trust_level"].map(TRUST_BADGES).fillna(frame["trust_level"])
    return frame[COLUMNS]


def _load_payload() -> dict[str, object]:
    if INDEX_URL:
        with urlopen(INDEX_URL, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {"rows": []}


with gr.Blocks(title="Agent Anvil Leaderboard") as demo:
    gr.Markdown(
        """
        # Agent Anvil Leaderboard

        Trace-aware CI eval results for tool-using agents. Rows are generated
        from `leaderboard_submission.json` artifacts and labeled by trust level
        instead of hiding the verification boundary.
        """
    )
    gr.Markdown(
        """
        ## Submit your agent

        Run the benchmark in your own repository, export a compact submission,
        and open a pull request to the public submissions repo. The Space never
        executes user agents or collects raw traces.

        ```bash
        uv run anvil paper reproduce
        uv run anvil leaderboard export docs/paper/results.json --manifest experiments/paper.yaml \\
          --out leaderboard_submission.json --agent-name "My Agent"
        uv run anvil leaderboard pr leaderboard_submission.json \\
          --leaderboard-repo ../agent-anvil-leaderboard
        ```

        Copy-paste workflow:
        [github-actions-submission.yml](https://github.com/agent-axiom/agent-anvil-leaderboard/blob/main/examples/github-actions-submission.yml).
        Verified reference:
        [agent-anvil-demo-agent](https://github.com/agent-axiom/agent-anvil-demo-agent)
        -> [Actions run](https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26335581868)
        -> [accepted PR](https://github.com/agent-axiom/agent-anvil-leaderboard/pull/1).

        Trust labels: `self_reported`, `github_actions`, `maintainer_rerun`.
        """
    )
    gr.Dataframe(
        value=load_rows,
        headers=COLUMNS,
        datatype=[
            "number",
            *["str"] * 5,
            *["number"] * 5,
            *["str"] * 8,
        ],
        interactive=False,
        wrap=True,
    )


if __name__ == "__main__":
    demo.launch()
