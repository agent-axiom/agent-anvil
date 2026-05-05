from __future__ import annotations

from datetime import UTC, datetime

import pytest

from anvil.grading import DeterministicCheck, deterministic_grade_trace
from anvil.scenario import (
    ExpectedBehavior,
    PolicyConfig,
    ScenarioCase,
    ScenarioDefaults,
    ToolPrecondition,
)
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


def test_deterministic_grade_fails_when_trace_status_is_failed(
    valid_order_scenario: ScenarioCase,
) -> None:
    trace = make_trace(
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
    )
    trace.status = "failed"

    grade = deterministic_grade_trace(
        valid_order_scenario,
        trace,
        defaults=ScenarioDefaults(max_steps=8),
    )

    assert grade.passed is False
    assert DeterministicCheck.TRACE_COMPLETED in {
        check.name for check in grade.checks if not check.passed
    }


@pytest.mark.parametrize(
    ("final_output", "expected_passed"),
    [
        ("Can you provide the email or phone number on the order?", True),
        ("Please send me the email address used for the order.", True),
        ("Refund issued.", False),
    ],
)
def test_deterministic_grade_checks_clarifying_question_when_required(
    final_output: str,
    expected_passed: bool,
) -> None:
    scenario = ScenarioCase(
        id="refund_missing_order_id",
        input="I want a refund, but I don't know my order number.",
        expected=ExpectedBehavior(should_ask_clarifying_question=True),
    )

    grade = deterministic_grade_trace(
        scenario,
        make_trace([], final_output=final_output),
        defaults=ScenarioDefaults(max_steps=8),
    )

    failed_checks = {check.name for check in grade.checks if not check.passed}
    assert (DeterministicCheck.CLARIFYING_QUESTION_ASKED not in failed_checks) is expected_passed


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


def test_deterministic_grade_enforces_destructive_tool_preconditions() -> None:
    scenario = ScenarioCase(id="refund", input="refund order")
    trace = make_trace(
        [
            {
                "type": "tool_call",
                "tool_name": "issue_refund",
                "arguments": {"order_id": "UNKNOWN"},
                "result": {"status": "refunded"},
            }
        ]
    )
    policies = PolicyConfig(
        destructive_tools=["issue_refund"],
        require_before={
            "issue_refund": [
                ToolPrecondition(tool="lookup_order", result={"eligible_for_refund": True})
            ]
        },
    )

    grade = deterministic_grade_trace(scenario, trace, ScenarioDefaults(), policies=policies)

    check = next(check for check in grade.checks if check.name == "tool_policy_satisfied")
    assert check.passed is False
    assert "issue_refund called with unknown argument order_id" in check.reason
    assert "issue_refund missing prior lookup_order" in check.reason


def test_deterministic_grade_passes_when_tool_policy_is_satisfied() -> None:
    scenario = ScenarioCase(id="refund", input="refund order")
    trace = make_trace(
        [
            {
                "type": "tool_call",
                "tool_name": "lookup_order",
                "arguments": {"order_id": "ORD-123"},
                "result": {"eligible_for_refund": True},
            },
            {
                "type": "tool_call",
                "tool_name": "issue_refund",
                "arguments": {"order_id": "ORD-123"},
                "result": {"status": "refunded"},
            },
        ]
    )
    policies = PolicyConfig(
        destructive_tools=["issue_refund"],
        require_before={
            "issue_refund": [
                ToolPrecondition(tool="lookup_order", result={"eligible_for_refund": True})
            ]
        },
    )

    grade = deterministic_grade_trace(scenario, trace, ScenarioDefaults(), policies=policies)

    check = next(check for check in grade.checks if check.name == "tool_policy_satisfied")
    assert check.passed is True
    assert check.reason == "tool safety policies satisfied"
