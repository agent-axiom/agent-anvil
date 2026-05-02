from __future__ import annotations

from pathlib import Path

from anvil.clustering import FailureCluster
from anvil.grading import GradeResult
from anvil.report import render_github_summary
from anvil.storage import load_results


def generate_github_summary(run_dir: str | Path) -> str:
    payload = load_results(run_dir)
    grades = [GradeResult.model_validate(item) for item in payload["grades"]]
    clusters = [FailureCluster.model_validate(item) for item in payload["clusters"]]
    return render_github_summary(
        suite_name=str(payload["suite"]),
        run_id=str(payload["run_id"]),
        total_scenarios=int(payload["summary"]["total_scenarios"]),
        grades=grades,
        clusters=clusters,
    )
