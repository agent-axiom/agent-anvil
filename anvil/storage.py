from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anvil.clustering import FailureCluster
from anvil.grading import GradeResult
from anvil.trace import TraceRun


def create_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}"


def create_run_dir(runs_dir: str | Path, run_id: str | None = None) -> Path:
    root = Path(runs_dir)
    root.mkdir(parents=True, exist_ok=True)
    selected_id = run_id or create_run_id()
    run_dir = root / selected_id
    suffix = 1
    while run_dir.exists():
        run_dir = root / f"{selected_id}_{suffix}"
        suffix += 1
    (run_dir / "traces").mkdir(parents=True)
    return run_dir


def write_trace(run_dir: Path, trace: TraceRun) -> Path:
    trace_path = run_dir / "traces" / f"{trace.scenario_id}_trial_{trace.trial}.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return trace_path


def write_results(
    *,
    run_dir: Path,
    suite_name: str,
    run_id: str,
    total_scenarios: int,
    grades: list[GradeResult],
    clusters: list[FailureCluster],
) -> Path:
    passed_trials = sum(1 for grade in grades if grade.passed)
    total_trials = len(grades)
    payload: dict[str, Any] = {
        "suite": suite_name,
        "run_id": run_id,
        "summary": {
            "total_scenarios": total_scenarios,
            "total_trials": total_trials,
            "passed_trials": passed_trials,
            "failed_trials": total_trials - passed_trials,
            "pass_rate": round((passed_trials / total_trials * 100) if total_trials else 0.0, 1),
        },
        "grades": [grade.model_dump(mode="json") for grade in grades],
        "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
    }
    results_path = run_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return results_path


def update_latest_link(runs_dir: str | Path, run_dir: Path) -> Path:
    latest = Path(runs_dir) / "latest"
    if latest.is_symlink() or latest.exists():
        if latest.is_dir() and not latest.is_symlink():
            shutil.rmtree(latest)
        else:
            latest.unlink()
    latest.symlink_to(run_dir.resolve(), target_is_directory=True)
    return latest


def load_results(run_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(run_dir) / "results.json").read_text(encoding="utf-8"))
