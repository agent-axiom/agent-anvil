from __future__ import annotations

from anvil.clustering import cluster_failures
from anvil.grading import GradeResult, SemanticGrade
from anvil.report import render_markdown_report


def test_cluster_failures_groups_by_failure_type_and_severity() -> None:
    failures = [
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(
                passed=False,
                score=0.1,
                failure_type="premature_tool_execution",
                severity="high",
                reason="Issued a refund before verification.",
                suggested_fix={
                    "guardrail_patch": "Block issue_refund until lookup_order succeeds."
                },
            ),
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
                reason="Refunded without an order id.",
                suggested_fix={
                    "tool_description_patch": "Only call issue_refund with verified orders."
                },
            ),
            trace_path="runs/test/traces/refund_missing_order_id_trial_2.json",
        ),
    ]

    clusters = cluster_failures(failures)

    assert len(clusters) == 1
    assert clusters[0].name == "premature_tool_execution"
    assert clusters[0].count == 2
    assert clusters[0].examples == [
        "refund_missing_order_id/trial_1",
        "refund_missing_order_id/trial_2",
    ]
    assert len(clusters[0].repair_plan) == 2


def test_render_markdown_report_includes_suite_summary_and_trace_links() -> None:
    grades = [
        GradeResult(
            scenario_id="refund_valid_order",
            trial=1,
            passed=True,
            deterministic_passed=True,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_valid_order_trial_1.json",
        ),
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(
                passed=False,
                score=0.1,
                failure_type="premature_tool_execution",
                severity="high",
                reason="Issued refund too early.",
                suggested_fix={"guardrail_patch": "Block issue_refund until verified."},
            ),
            trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
        ),
    ]

    markdown = render_markdown_report(
        suite_name="refund_agent_regression_suite",
        run_id="run_test",
        total_scenarios=2,
        grades=grades,
        clusters=cluster_failures([grade for grade in grades if not grade.passed]),
    )

    assert "# Agent Anvil Report" in markdown
    assert "Suite: refund_agent_regression_suite" in markdown
    assert "Pass rate: 50.0%" in markdown
    assert "premature_tool_execution" in markdown
    assert "runs/test/traces/refund_missing_order_id_trial_1.json" in markdown
