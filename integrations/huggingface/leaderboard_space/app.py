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

COLUMNS = [
    "rank",
    "agent_name",
    "agent_version",
    "benchmark_name",
    "trust_level",
    "trace_aware_pass_rate",
    "final_answer_pass_rate",
    "answer_only_missed_failures",
    "answer_only_missed_failure_rate",
    "total_trials",
    "repo_url",
    "commit_sha",
    "github_run_url",
    "evidence_sha256",
]


def load_rows() -> Any:
    payload = _load_payload()
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    return pd.DataFrame(rows, columns=COLUMNS)


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
    gr.Dataframe(
        value=load_rows,
        headers=COLUMNS,
        datatype=[
            "number",
            *["str"] * 4,
            "number",
            "number",
            "number",
            "number",
            "number",
            *["str"] * 4,
        ],
        interactive=False,
        wrap=True,
    )


if __name__ == "__main__":
    demo.launch()
