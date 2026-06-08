from __future__ import annotations

from datetime import UTC, datetime

import pytest

from anvil.grading import deterministic_grade_trace
from anvil.scenario import AssertionCheck, ExpectedBehavior, ScenarioCase, ScenarioDefaults
from anvil.trace import TraceRun


def make_trace(steps: list[dict[str, object]], final_output: str = "Refund issued.") -> TraceRun:
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
    )


def expected_with_assertions(assertions: list[dict[str, object]]) -> ExpectedBehavior:
    return ExpectedBehavior.model_validate({"assertions": assertions})


def test_assertion_schema_accepts_v1_tool_and_output_assertions() -> None:
    expected = expected_with_assertions(
        [
            {"type": "tool_called", "tool": "lookup_order"},
            {"type": "tool_not_called", "tool": "issue_refund"},
            {"type": "tool_called_before", "before": "issue_refund", "after": "lookup_order"},
            {"type": "tool_sequence", "tools": ["lookup_order", "issue_refund"]},
            {"type": "min_tool_calls", "tool": "lookup_order", "count": 1},
            {"type": "max_tool_calls", "tool": "lookup_order", "count": 1},
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
        ]
    )

    assert len(expected.assertions) == 10
    assert isinstance(expected.assertions[0], AssertionCheck)
    assert expected.assertions[6].values == ["UNKNOWN", "", None]


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
