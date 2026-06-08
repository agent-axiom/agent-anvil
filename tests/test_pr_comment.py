from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.grading import HeuristicSemanticGrader
from anvil.pr_comment import generate_pr_comment, write_pr_comment
from anvil.runner import run_suite


def test_generate_pr_comment_highlights_top_failure(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )

    comment = generate_pr_comment(result.run_dir)

    assert "## Agent Anvil PR Review" in comment
    assert "New agent regression" in comment
    assert "premature_tool_execution / high" in comment
    assert "refund_missing_order_id/trial_1" in comment
    assert "runs/latest/traces" in comment


def test_generate_pr_comment_highlights_flaky_scenarios(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "suite": "refund_agent_regression_suite",
                "run_id": "run_test",
                "summary": {
                    "total_scenarios": 1,
                    "total_trials": 2,
                    "passed_trials": 1,
                    "failed_trials": 1,
                    "pass_rate": 50.0,
                    "flaky_scenarios": [
                        {
                            "scenario_id": "refund_missing_order_id",
                            "passed_trials": 1,
                            "failed_trials": 1,
                            "total_trials": 2,
                            "pass_rate": 50.0,
                        }
                    ],
                },
                "grades": [
                    {
                        "scenario_id": "refund_missing_order_id",
                        "trial": 1,
                        "passed": True,
                        "deterministic_passed": True,
                        "semantic": {"passed": True, "score": 1.0},
                        "trace_path": "runs/test/traces/refund_missing_order_id_trial_1.json",
                        "deterministic_checks": [],
                    },
                    {
                        "scenario_id": "refund_missing_order_id",
                        "trial": 2,
                        "passed": False,
                        "deterministic_passed": False,
                        "semantic": {
                            "passed": False,
                            "score": 0.1,
                            "failure_type": "premature_tool_execution",
                            "severity": "high",
                        },
                        "trace_path": "runs/test/traces/refund_missing_order_id_trial_2.json",
                        "deterministic_checks": [],
                    },
                ],
                "clusters": [],
            }
        ),
        encoding="utf-8",
    )

    comment = generate_pr_comment(run_dir)

    assert "### Flaky scenarios" in comment
    assert "- `refund_missing_order_id`: 1/2 trials passed (50.0%)" in comment


def test_write_pr_comment_and_cli(tmp_path: Path, scenario_file: Path) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )
    out = tmp_path / "comment.md"

    path = write_pr_comment(result.run_dir, out_path=out)
    cli_result = CliRunner().invoke(app, ["pr-comment", str(result.run_dir), "--out", str(out)])

    assert path == out
    assert out.exists()
    assert cli_result.exit_code == 0
    assert f"Wrote {out}" in cli_result.stdout
