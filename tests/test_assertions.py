from __future__ import annotations

from datetime import UTC, datetime

import pytest

from anvil.grading import deterministic_grade_trace
from anvil.scenario import AssertionCheck, ExpectedBehavior, ScenarioCase, ScenarioDefaults
from anvil.trace import TraceMetrics, TraceRun


def make_trace(
    steps: list[dict[str, object]],
    final_output: str = "Refund issued.",
    metrics: TraceMetrics | None = None,
) -> TraceRun:
    return TraceRun(
        run_id="run_test",
        scenario_id="assertions",
        trial=1,
        input="Please refund ORD-123.",
        started_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 10, 12, 0, 2, tzinfo=UTC),
        status="completed",
        steps=steps,
        final_output=final_output,
        metrics=metrics or TraceMetrics(),
    )


def expected_with_assertions(assertions: list[dict[str, object]]) -> ExpectedBehavior:
    return ExpectedBehavior.model_validate({"assertions": assertions})


def test_assertion_schema_accepts_v1_tool_and_output_assertions() -> None:
    expected = expected_with_assertions(
        [
            {"type": "tool_called", "tool": "lookup_order"},
            {"type": "tool_not_called", "tool": "delete_account"},
            {"type": "tool_called_before", "before": "issue_refund", "after": "lookup_order"},
            {"type": "tool_sequence", "tools": ["lookup_order", "issue_refund"]},
            {"type": "min_tool_calls", "tool": "lookup_order", "count": 1},
            {"type": "max_tool_calls", "tool": "lookup_order", "count": 1},
            {
                "type": "tool_argument_matches",
                "tool": "issue_refund",
                "path": "$.order_id",
                "equals": "ORD-123",
            },
            {
                "type": "forbidden_arg_value",
                "tool": "issue_refund",
                "path": "$.order_id",
                "values": ["UNKNOWN", "", None],
            },
            {
                "type": "tool_result_matches",
                "tool": "lookup_order",
                "path": "$.eligible_for_refund",
                "equals": True,
            },
            {"type": "final_output_contains", "text": "refund"},
            {"type": "final_output_not_contains", "text": "guaranteed"},
            {"type": "metric_lte", "metric": "latency_ms", "value": 2500},
            {"type": "metric_gte", "metric": "total_tokens", "value": 100},
            {"type": "no_tool_errors"},
            {"type": "tool_retried_after_error", "tool": "lookup_order"},
        ]
    )

    assert len(expected.assertions) == 15
    assert isinstance(expected.assertions[0], AssertionCheck)
    assert expected.assertions[7].values == ["UNKNOWN", "", None]


@pytest.mark.parametrize("assertion_type", ["tool_argument_matches", "tool_result_matches"])
def test_match_assertions_require_explicit_equals(assertion_type: str) -> None:
    with pytest.raises(ValueError, match="missing required fields: equals"):
        expected_with_assertions(
            [{"type": assertion_type, "tool": "lookup_order", "path": "$.verified"}]
        )


@pytest.mark.parametrize("assertion_type", ["tool_argument_matches", "tool_result_matches"])
def test_match_assertions_accept_explicit_null_equals(assertion_type: str) -> None:
    expected = expected_with_assertions(
        [
            {
                "type": assertion_type,
                "tool": "lookup_order",
                "path": "$.verified",
                "equals": None,
            }
        ]
    )

    assert expected.assertions[0].equals is None


@pytest.mark.parametrize("assertion_type", ["metric_lte", "metric_gte"])
def test_metric_assertions_require_metric_and_value(assertion_type: str) -> None:
    with pytest.raises(ValueError, match="missing required fields: metric, value"):
        expected_with_assertions([{"type": assertion_type}])


def test_metric_assertions_reject_negative_values() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        expected_with_assertions(
            [{"type": "metric_lte", "metric": "estimated_cost_usd", "value": -0.01}]
        )


def test_tool_retried_after_error_assertion_requires_tool() -> None:
    with pytest.raises(ValueError, match="missing required fields: tool"):
        expected_with_assertions([{"type": "tool_retried_after_error"}])


@pytest.mark.parametrize(
    ("assertion", "steps", "passed", "reason"),
    [
        (
            {"type": "tool_called", "tool": "lookup_order"},
            [{"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}}],
            True,
            "assertion passed",
        ),
        (
            {"type": "tool_not_called", "tool": "issue_refund"},
            [{"type": "tool_call", "tool_name": "issue_refund", "arguments": {}, "result": {}}],
            False,
            "issue_refund was called",
        ),
        (
            {"type": "tool_called_before", "before": "issue_refund", "after": "lookup_order"},
            [
                {"type": "tool_call", "tool_name": "issue_refund", "arguments": {}, "result": {}},
                {"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}},
            ],
            False,
            "lookup_order was not called before issue_refund",
        ),
        (
            {"type": "tool_sequence", "tools": ["lookup_order", "issue_refund"]},
            [
                {"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}},
                {"type": "tool_call", "tool_name": "issue_refund", "arguments": {}, "result": {}},
            ],
            True,
            "assertion passed",
        ),
        (
            {"type": "tool_sequence", "tools": ["lookup_order", "issue_refund"]},
            [
                {"type": "tool_call", "tool_name": "issue_refund", "arguments": {}, "result": {}},
                {"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}},
            ],
            False,
            "tool sequence expected lookup_order -> issue_refund, got issue_refund -> lookup_order",
        ),
        (
            {"type": "min_tool_calls", "tool": "lookup_order", "count": 2},
            [{"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}}],
            False,
            "lookup_order called 1 times, min is 2",
        ),
        (
            {"type": "max_tool_calls", "tool": "lookup_order", "count": 1},
            [
                {"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}},
                {"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}},
            ],
            False,
            "lookup_order called 2 times, max is 1",
        ),
        (
            {
                "type": "tool_argument_matches",
                "tool": "issue_refund",
                "path": "$.order_id",
                "equals": "ORD-123",
            },
            [
                {
                    "type": "tool_call",
                    "tool_name": "issue_refund",
                    "arguments": {"order_id": "UNKNOWN"},
                    "result": {},
                }
            ],
            False,
            "issue_refund argument $.order_id expected 'ORD-123', got 'UNKNOWN'",
        ),
        (
            {
                "type": "forbidden_arg_value",
                "tool": "issue_refund",
                "path": "$.order_id",
                "values": ["UNKNOWN"],
            },
            [
                {
                    "type": "tool_call",
                    "tool_name": "issue_refund",
                    "arguments": {"order_id": "UNKNOWN"},
                    "result": {},
                }
            ],
            False,
            "issue_refund argument $.order_id had forbidden value 'UNKNOWN'",
        ),
        (
            {
                "type": "tool_result_matches",
                "tool": "lookup_order",
                "path": "$.eligible_for_refund",
                "equals": True,
            },
            [
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {},
                    "result": {"eligible_for_refund": False},
                }
            ],
            False,
            "lookup_order result $.eligible_for_refund expected True, got False",
        ),
        (
            {"type": "no_tool_errors"},
            [
                {
                    "type": "tool_argument_error",
                    "tool_name": "issue_refund",
                    "arguments": {"order_id": "ORD-123"},
                    "error": "invalid args",
                }
            ],
            False,
            "tool errors observed: tool_argument_error(issue_refund)",
        ),
        (
            {"type": "no_tool_errors", "tool": "issue_refund"},
            [
                {
                    "type": "tool_execution_error",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-123"},
                    "error": "timeout",
                }
            ],
            True,
            "assertion passed",
        ),
        (
            {"type": "tool_retried_after_error", "tool": "lookup_order"},
            [
                {
                    "type": "tool_execution_error",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-123"},
                    "error": "timeout",
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-123"},
                    "result": {"status": "found"},
                },
            ],
            True,
            "assertion passed",
        ),
        (
            {"type": "tool_retried_after_error", "tool": "lookup_order"},
            [
                {
                    "type": "tool_execution_error",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-123"},
                    "error": "timeout",
                }
            ],
            False,
            "lookup_order error was not followed by retry",
        ),
        (
            {"type": "tool_retried_after_error", "tool": "lookup_order"},
            [{"type": "tool_call", "tool_name": "lookup_order", "arguments": {}, "result": {}}],
            False,
            "lookup_order error was not observed",
        ),
    ],
)
def test_deterministic_assertion_checks_tool_trace_behavior(
    assertion: dict[str, object],
    steps: list[dict[str, object]],
    passed: bool,
    reason: str,
) -> None:
    scenario = ScenarioCase(
        id="assertions",
        input="Please refund ORD-123.",
        expected=expected_with_assertions([assertion]),
    )

    grade = deterministic_grade_trace(scenario, make_trace(steps), ScenarioDefaults())

    assertion_check = next(check for check in grade.checks if check.name == "assertions_satisfied")
    assert assertion_check.passed is passed
    assert reason in assertion_check.reason


@pytest.mark.parametrize(
    ("assertion", "final_output", "passed", "reason"),
    [
        (
            {"type": "final_output_contains", "text": "refund issued"},
            "Refund issued for ORD-123.",
            True,
            "assertion passed",
        ),
        (
            {"type": "final_output_contains", "text": "refund issued"},
            "I need more information.",
            False,
            "final output does not contain 'refund issued'",
        ),
        (
            {"type": "final_output_not_contains", "text": "guaranteed"},
            "This refund is guaranteed.",
            False,
            "final output contains forbidden text 'guaranteed'",
        ),
    ],
)
def test_deterministic_assertion_checks_final_output(
    assertion: dict[str, object],
    final_output: str,
    passed: bool,
    reason: str,
) -> None:
    scenario = ScenarioCase(
        id="assertions",
        input="Please refund ORD-123.",
        expected=expected_with_assertions([assertion]),
    )

    grade = deterministic_grade_trace(scenario, make_trace([], final_output), ScenarioDefaults())

    assertion_check = next(check for check in grade.checks if check.name == "assertions_satisfied")
    assert assertion_check.passed is passed
    assert reason in assertion_check.reason


@pytest.mark.parametrize(
    ("assertion", "metrics", "passed", "reason"),
    [
        (
            {"type": "metric_lte", "metric": "latency_ms", "value": 2500},
            TraceMetrics(),
            True,
            "assertion passed",
        ),
        (
            {"type": "metric_lte", "metric": "latency_ms", "value": 1000},
            TraceMetrics(),
            False,
            "metric latency_ms expected <= 1000, got 2000",
        ),
        (
            {"type": "metric_lte", "metric": "estimated_cost_usd", "value": 0.01},
            TraceMetrics(estimated_cost_usd=0.02),
            False,
            "metric estimated_cost_usd expected <= 0.01, got 0.02",
        ),
        (
            {"type": "metric_gte", "metric": "total_tokens", "value": 100},
            TraceMetrics(total_tokens=225),
            True,
            "assertion passed",
        ),
    ],
)
def test_deterministic_assertion_checks_trace_metrics(
    assertion: dict[str, object],
    metrics: TraceMetrics,
    passed: bool,
    reason: str,
) -> None:
    scenario = ScenarioCase(
        id="assertions",
        input="Please refund ORD-123.",
        expected=expected_with_assertions([assertion]),
    )

    grade = deterministic_grade_trace(
        scenario,
        make_trace([], metrics=metrics),
        ScenarioDefaults(),
    )

    assertion_check = next(check for check in grade.checks if check.name == "assertions_satisfied")
    assert assertion_check.passed is passed
    assert reason in assertion_check.reason
