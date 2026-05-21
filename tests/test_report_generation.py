from __future__ import annotations

from anvil.clustering import cluster_failures
from anvil.grading import CheckOutcome, DeterministicCheck, GradeResult, SemanticGrade
from anvil.report import render_github_summary, render_markdown_report


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


def test_cluster_failures_falls_back_to_failed_deterministic_check() -> None:
    failures = [
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
            deterministic_checks=[
                CheckOutcome(
                    name=DeterministicCheck.EXPECTED_TOOLS_CALLED,
                    passed=False,
                    reason="missing expected tool calls: lookup_customer",
                )
            ],
        )
    ]

    clusters = cluster_failures(failures)

    assert clusters[0].name == "expected_tools_called"
    assert clusters[0].severity == "medium"
    assert clusters[0].repair_plan == [
        "Update the agent prompt or tool policy so expected tools are called: "
        "missing expected tool calls: lookup_customer"
    ]


def test_cluster_failures_handles_assertion_failures() -> None:
    failures = [
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
            deterministic_checks=[
                CheckOutcome(
                    name=DeterministicCheck.ASSERTIONS_SATISFIED,
                    passed=False,
                    reason="issue_refund should not be called",
                )
            ],
        )
    ]

    clusters = cluster_failures(failures)

    assert clusters[0].name == "assertions_satisfied"
    assert clusters[0].severity == "high"
    assert clusters[0].repair_plan == [
        "Update scenario assertions or agent behavior to satisfy trace invariants: "
        "issue_refund should not be called"
    ]


def test_cluster_failures_uses_deterministic_repairs_when_semantic_fix_is_empty() -> None:
    failures = [
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(
                passed=False,
                score=0.0,
                failure_type="instruction_violation",
                severity="high",
                reason="Issued refund with unknown order.",
                suggested_fix={
                    "prompt_patch": "",
                    "tool_description_patch": "",
                    "guardrail_patch": "",
                },
            ),
            trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
            deterministic_checks=[
                CheckOutcome(
                    name=DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED,
                    passed=False,
                    reason="forbidden tool calls observed: issue_refund",
                )
            ],
        )
    ]

    clusters = cluster_failures(failures)

    assert clusters[0].name == "instruction_violation"
    assert clusters[0].repair_plan == [
        "Add a guardrail before forbidden or destructive tool calls: "
        "forbidden tool calls observed: issue_refund"
    ]


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


def test_render_github_summary_highlights_failure_clusters() -> None:
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

    summary = render_github_summary(
        suite_name="refund_agent_regression_suite",
        run_id="run_test",
        total_scenarios=2,
        grades=grades,
        clusters=cluster_failures([grade for grade in grades if not grade.passed]),
    )

    assert "## Agent Anvil Summary" in summary
    assert "| Pass rate | 50.0% |" in summary
    assert "| premature_tool_execution | high | 1 |" in summary
    assert "Block issue_refund until verified." in summary
    assert "refund_missing_order_id/trial_1" in summary
