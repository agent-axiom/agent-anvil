from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from anvil.grading import CheckOutcome, DeterministicCheck, GradeResult


class OutcomeCategory(StrEnum):
    PASS = "pass"
    PROTOCOL_ERROR = "protocol_error"
    POLICY_VIOLATION = "policy_violation"
    ASSERTION_FAILURE = "assertion_failure"
    DETERMINISTIC_FAILURE = "deterministic_failure"
    SEMANTIC_FAILURE = "semantic_failure"
    UNKNOWN_FAILURE = "unknown_failure"


class OutcomeClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: OutcomeCategory
    failure_type: str
    severity: str
    reason: str


def classify_grade(grade: GradeResult) -> OutcomeClassification:
    if grade.passed:
        return OutcomeClassification(
            category=OutcomeCategory.PASS,
            failure_type="none",
            severity="none",
            reason="trial passed",
        )

    failed_checks = [check for check in grade.deterministic_checks if not check.passed]
    deterministic_outcome = _deterministic_outcome(failed_checks)
    if deterministic_outcome is not None:
        return deterministic_outcome

    if not grade.semantic.passed:
        return OutcomeClassification(
            category=OutcomeCategory.SEMANTIC_FAILURE,
            failure_type=grade.semantic.failure_type,
            severity=grade.semantic.severity,
            reason=grade.semantic.reason,
        )

    return OutcomeClassification(
        category=OutcomeCategory.UNKNOWN_FAILURE,
        failure_type="unknown_failure",
        severity="medium",
        reason="trial failed without deterministic or semantic failure details",
    )


def deterministic_severity(check: DeterministicCheck) -> str:
    if check in {
        DeterministicCheck.TRACE_COMPLETED,
        DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED,
        DeterministicCheck.REQUIRED_TOOL_ARGS_MATCHED,
        DeterministicCheck.FINAL_OUTPUT_EXISTS,
        DeterministicCheck.TOOL_POLICY_SATISFIED,
        DeterministicCheck.ASSERTIONS_SATISFIED,
    }:
        return "high"
    return "medium"


def _deterministic_outcome(
    failed_checks: Sequence[CheckOutcome],
) -> OutcomeClassification | None:
    priority = (
        (DeterministicCheck.TRACE_COMPLETED, OutcomeCategory.PROTOCOL_ERROR),
        (DeterministicCheck.TOOL_POLICY_SATISFIED, OutcomeCategory.POLICY_VIOLATION),
        (DeterministicCheck.ASSERTIONS_SATISFIED, OutcomeCategory.ASSERTION_FAILURE),
    )
    failed_check_names = {check.name for check in failed_checks}
    for check_name, category in priority:
        if check_name in failed_check_names:
            return _from_check(category, _first_check(failed_checks, check_name))
    if failed_checks:
        return _from_check(OutcomeCategory.DETERMINISTIC_FAILURE, failed_checks[0])
    return None


def _from_check(category: OutcomeCategory, check: CheckOutcome) -> OutcomeClassification:
    return OutcomeClassification(
        category=category,
        failure_type=check.name.value,
        severity=deterministic_severity(check.name),
        reason=check.reason,
    )


def _first_check(checks: Sequence[CheckOutcome], name: DeterministicCheck) -> CheckOutcome:
    return next(check for check in checks if check.name == name)
