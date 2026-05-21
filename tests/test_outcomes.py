from __future__ import annotations

import pytest

from anvil.grading import CheckOutcome, DeterministicCheck, GradeResult, SemanticGrade
from anvil.outcomes import OutcomeCategory, classify_grade


def test_classify_grade_pass() -> None:
    grade = _grade(passed=True)

    outcome = classify_grade(grade)

    assert outcome.category == OutcomeCategory.PASS
    assert outcome.failure_type == "none"
    assert outcome.severity == "none"


@pytest.mark.parametrize(
    ("check_name", "category", "severity"),
    [
        (
            DeterministicCheck.TRACE_COMPLETED,
            OutcomeCategory.PROTOCOL_ERROR,
            "high",
        ),
        (
            DeterministicCheck.TOOL_POLICY_SATISFIED,
            OutcomeCategory.POLICY_VIOLATION,
            "high",
        ),
        (
            DeterministicCheck.ASSERTIONS_SATISFIED,
            OutcomeCategory.ASSERTION_FAILURE,
            "high",
        ),
        (
            DeterministicCheck.EXPECTED_TOOLS_CALLED,
            OutcomeCategory.DETERMINISTIC_FAILURE,
            "medium",
        ),
    ],
)
def test_classify_grade_deterministic_failures(
    check_name: DeterministicCheck,
    category: OutcomeCategory,
    severity: str,
) -> None:
    grade = _grade(
        passed=False,
        deterministic_passed=False,
        deterministic_checks=[
            CheckOutcome(name=check_name, passed=False, reason=f"{check_name.value} failed")
        ],
    )

    outcome = classify_grade(grade)

    assert outcome.category == category
    assert outcome.failure_type == check_name.value
    assert outcome.severity == severity
    assert outcome.reason == f"{check_name.value} failed"


def test_classify_grade_prefers_policy_over_generic_forbidden_tool_failure() -> None:
    grade = _grade(
        passed=False,
        deterministic_passed=False,
        deterministic_checks=[
            CheckOutcome(
                name=DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED,
                passed=False,
                reason="forbidden tool called",
            ),
            CheckOutcome(
                name=DeterministicCheck.TOOL_POLICY_SATISFIED,
                passed=False,
                reason="destructive tool missing precondition",
            ),
        ],
    )

    outcome = classify_grade(grade)

    assert outcome.category == OutcomeCategory.POLICY_VIOLATION
    assert outcome.failure_type == "tool_policy_satisfied"


def test_classify_grade_semantic_failure() -> None:
    grade = _grade(
        passed=False,
        deterministic_passed=True,
        semantic=SemanticGrade(
            passed=False,
            score=0.2,
            failure_type="instruction_violation",
            severity="medium",
            reason="Ignored the task instruction.",
        ),
    )

    outcome = classify_grade(grade)

    assert outcome.category == OutcomeCategory.SEMANTIC_FAILURE
    assert outcome.failure_type == "instruction_violation"
    assert outcome.severity == "medium"
    assert outcome.reason == "Ignored the task instruction."


def _grade(
    *,
    passed: bool,
    deterministic_passed: bool = True,
    deterministic_checks: list[CheckOutcome] | None = None,
    semantic: SemanticGrade | None = None,
) -> GradeResult:
    return GradeResult(
        scenario_id="scenario",
        trial=1,
        passed=passed,
        deterministic_passed=deterministic_passed,
        semantic=semantic or SemanticGrade(passed=True, score=1.0),
        trace_path="runs/test/traces/scenario_trial_1.json",
        deterministic_checks=deterministic_checks or [],
    )
