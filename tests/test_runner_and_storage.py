from __future__ import annotations

import json
from pathlib import Path

from anvil.grading import HeuristicSemanticGrader
from anvil.runner import run_suite


def test_run_suite_writes_trace_results_report_and_latest_link(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"

    result = run_suite(
        scenario_file,
        runs_dir=runs_dir,
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )

    assert result.total_trials == 2
    assert result.passed_trials == 1
    assert result.pass_rate == 50.0
    assert result.run_dir.exists()
    assert (result.run_dir / "report.md").exists()
    assert (result.run_dir / "results.json").exists()
    assert len(list((result.run_dir / "traces").glob("*.json"))) == 2
    assert (runs_dir / "latest").exists()

    payload = json.loads((result.run_dir / "results.json").read_text(encoding="utf-8"))
    assert payload["suite"] == "refund_agent_regression_suite"
    assert payload["summary"]["pass_rate"] == 50.0
    assert payload["clusters"][0]["name"] == "premature_tool_execution"


def test_run_suite_allows_trial_override(scenario_file: Path, tmp_path: Path) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=2,
        semantic_grader=HeuristicSemanticGrader(),
    )

    assert result.total_trials == 4
    assert len(result.grades) == 4


def test_patched_support_agent_passes_refund_suite(tmp_path: Path) -> None:
    result = run_suite(
        "scenarios/refund_agent_patched.yaml",
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )

    assert result.total_trials == 2
    assert result.passed_trials == 2
    assert result.pass_rate == 100.0


def test_tool_safety_suite_catches_generic_agent_failures(tmp_path: Path) -> None:
    result = run_suite(
        "scenarios/tool_safety.yaml",
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )

    assert result.total_trials == 3
    assert result.passed_trials == 0
    assert result.pass_rate == 0.0
    assert {cluster.name for cluster in result.clusters} == {
        "premature_tool_execution",
        "required_tool_args_matched",
        "max_steps_not_exceeded",
    }
