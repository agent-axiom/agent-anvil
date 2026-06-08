from __future__ import annotations

import json

from anvil.grading import GradeResult, SemanticGrade
from anvil.storage import write_results


def test_write_results_persists_flaky_scenario_summary(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    grades = [
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=True,
            deterministic_passed=True,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
        ),
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=2,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(
                passed=False,
                score=0.2,
                failure_type="premature_tool_execution",
                severity="high",
            ),
            trace_path="runs/test/traces/refund_missing_order_id_trial_2.json",
        ),
        GradeResult(
            scenario_id="refund_valid_order",
            trial=1,
            passed=True,
            deterministic_passed=True,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_valid_order_trial_1.json",
        ),
    ]

    results_path = write_results(
        run_dir=run_dir,
        suite_name="refund_agent_regression_suite",
        run_id="run_test",
        total_scenarios=2,
        grades=grades,
        clusters=[],
    )

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["summary"]["flaky_scenarios"] == [
        {
            "scenario_id": "refund_missing_order_id",
            "passed_trials": 1,
            "failed_trials": 1,
            "total_trials": 2,
            "pass_rate": 50.0,
        }
    ]
