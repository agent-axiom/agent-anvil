from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from leaderboard_view import (
    DISPLAY_COLUMNS,
    filter_rows,
    normalize_rows,
    summary_markdown,
    table_values,
)

gr: Any = import_module("gradio")

INDEX_URL = os.getenv(
    "LEADERBOARD_INDEX_URL",
    "https://huggingface.co/datasets/ifif/agent-anvil-leaderboard-data/resolve/main/leaderboard.json",
)
INDEX_PATH = Path(os.getenv("LEADERBOARD_INDEX_PATH", "leaderboard.json"))


def load_rows() -> list[dict[str, Any]]:
    return normalize_rows(_load_payload())


def render_leaderboard(
    search: str,
    trust_level: str,
    min_trials: int | float,
    freshness: str,
    sort_by: str,
    descending: bool,
) -> tuple[str, list[list[Any]]]:
    rows = filter_rows(
        load_rows(),
        search=search,
        trust_level=trust_level,
        min_trials=min_trials,
        freshness=freshness,
        sort_by=sort_by,
        descending=descending,
    )
    return summary_markdown(rows), table_values(rows)


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
        -> [Actions run](https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26336840349)
        -> [accepted PR](https://github.com/agent-axiom/agent-anvil-leaderboard/pull/5).

        Trust labels: `self_reported`, `github_actions`, `maintainer_rerun`.
        """
    )
    with gr.Row():
        search = gr.Textbox(label="Search", placeholder="agent name, version, repository")
        trust_level = gr.Dropdown(
            label="Trust",
            choices=["all", "maintainer_rerun", "github_actions", "self_reported"],
            value="all",
        )
        min_trials = gr.Slider(label="Minimum trials", minimum=0, maximum=500, step=10, value=0)
        freshness = gr.Dropdown(
            label="Freshness",
            choices=["all", "fresh", "aging", "stale", "unknown"],
            value="all",
        )
    with gr.Row():
        sort_by = gr.Dropdown(
            label="Sort by",
            choices=[
                "trace_aware_pass_rate",
                "final_answer_pass_rate",
                "answer_only_missed_failure_rate",
                "answer_only_missed_failures",
                "total_trials",
                "rank",
            ],
            value="trace_aware_pass_rate",
        )
        descending = gr.Checkbox(label="Descending", value=True)

    initial_summary, initial_table = render_leaderboard(
        search="",
        trust_level="all",
        min_trials=0,
        freshness="all",
        sort_by="trace_aware_pass_rate",
        descending=True,
    )
    summary = gr.Markdown(value=initial_summary)
    table = gr.Dataframe(
        value=initial_table,
        headers=DISPLAY_COLUMNS,
        datatype=["number", *["str"] * 3, *["number"] * 5, *["str"] * 4],
        interactive=False,
        wrap=True,
    )

    for control in (search, trust_level, min_trials, freshness, sort_by, descending):
        control.change(
            render_leaderboard,
            inputs=[search, trust_level, min_trials, freshness, sort_by, descending],
            outputs=[summary, table],
        )


if __name__ == "__main__":
    demo.launch()
