from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from anvil.grading import DeterministicCheck, GradeResult


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
    failed_check_names = {check.name for check in failed_checks}
    if DeterministicCheck.TRACE_COMPLETED in failed_check_names:
        check = _first_check(failed_checks, DeterministicCheck.TRACE_COMPLETED)
        return _from_check(OutcomeCategory.PROTOCOL_ERROR, check)
    if DeterministicCheck.TOOL_POLICY_SATISFIED in failed_check_names:
        check = _first_check(failed_checks, DeterministicCheck.TOOL_POLICY_SATISFIED)
        return _from_check(OutcomeCategory.POLICY_VIOLATION, check)
    if DeterministicCheck.ASSERTIONS_SATISFIED in failed_check_names:
        check = _first_check(failed_checks, DeterministicCheck.ASSERTIONS_SATISFIED)
        return _from_check(OutcomeCategory.ASSERTION_FAILURE, check)
    if failed_checks:
        return _from_check(OutcomeCategory.DETERMINISTIC_FAILURE, failed_checks[0])

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


def _from_check(category: OutcomeCategory, check: object) -> OutcomeClassification:
    name = getattr(check, "name")
    reason = getattr(check, "reason")
    return OutcomeClassification(
        category=category,
        failure_type=name.value,
        severity=deterministic_severity(name),
        reason=reason,
    )


def _first_check(checks: list[object], name: DeterministicCheck) -> object:
    return next(check for check in checks if getattr(check, "name") == name)
