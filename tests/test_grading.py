from __future__ import annotations

from datetime import UTC, datetime

import pytest

from anvil.grading import DeterministicCheck, deterministic_grade_trace
from anvil.scenario import ExpectedBehavior, ScenarioCase, ScenarioDefaults
from anvil.trace import TraceRun


@pytest.fixture
def valid_order_scenario() -> ScenarioCase:
    return ScenarioCase(
        id="refund_valid_order",
        input="Please refund order ORD-123. It arrived broken.",
        expected=ExpectedBehavior(
            should_call_tools=["lookup_order", "issue_refund"],
            required_tool_args={"issue_refund": {"order_id": "ORD-123"}},
            success_criteria=["Looks up the order before issuing refund"],
        ),
    )


def make_trace(steps: list[dict[str, object]], final_output: str | None = "Done.") -> TraceRun:
    return TraceRun(
        run_id="run_test",
        scenario_id="refund_valid_order",
        trial=1,
        input="Please refund order ORD-123. It arrived broken.",
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 2, tzinfo=UTC),
        status="completed",
        steps=steps,
        final_output=final_output,
    )


@pytest.mark.parametrize(
    ("steps", "expected_passed"),
    [
        (
            [
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-123"},
                    "result": {"status": "found"},
                },
                {
                    "type": "tool_call",
                    "tool_name": "issue_refund",
                    "arguments": {"order_id": "ORD-123", "reason": "broken"},
                    "result": {"status": "refunded"},
                },
            ],
            True,
        ),
        (
            [
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-999"},
                    "result": {"status": "found"},
                },
                {
                    "type": "tool_call",
                    "tool_name": "issue_refund",
                    "arguments": {"order_id": "ORD-999", "reason": "broken"},
                    "result": {"status": "refunded"},
                },
            ],
            False,
        ),
    ],
)
def test_deterministic_grade_checks_required_tool_args(
    valid_order_scenario: ScenarioCase,
    steps: list[dict[str, object]],
    expected_passed: bool,
) -> None:
    grade = deterministic_grade_trace(
        valid_order_scenario,
        make_trace(steps),
        defaults=ScenarioDefaults(max_steps=8),
    )

    assert grade.passed is expected_passed


def test_deterministic_grade_reports_forbidden_tool_call() -> None:
    scenario = ScenarioCase(
        id="refund_missing_order_id",
        input="I want a refund, but I don't know my order number.",
        expected=ExpectedBehavior(
            should_call_tools=["lookup_customer"],
            should_not_call_tools=["issue_refund"],
            should_ask_clarifying_question=True,
        ),
    )
    trace = make_trace(
        [
            {
                "type": "tool_call",
                "tool_name": "issue_refund",
                "arguments": {"order_id": "UNKNOWN", "reason": "customer asked"},
                "result": {"status": "refunded"},
            }
        ],
        final_output="Refund issued.",
    )

    grade = deterministic_grade_trace(scenario, trace, defaults=ScenarioDefaults(max_steps=8))

    assert grade.passed is False
    assert DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED in {
        check.name for check in grade.checks if not check.passed
    }
