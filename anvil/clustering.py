from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from anvil.grading import CheckOutcome, DeterministicCheck, GradeResult

DETERMINISTIC_SEVERITY = {
    DeterministicCheck.TRACE_COMPLETED: "high",
    DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED: "high",
    DeterministicCheck.REQUIRED_TOOL_ARGS_MATCHED: "high",
    DeterministicCheck.FINAL_OUTPUT_EXISTS: "high",
    DeterministicCheck.EXPECTED_TOOLS_CALLED: "medium",
    DeterministicCheck.MAX_STEPS_NOT_EXCEEDED: "medium",
    DeterministicCheck.CLARIFYING_QUESTION_ASKED: "medium",
}

DETERMINISTIC_REPAIR_PREFIX = {
    DeterministicCheck.TRACE_COMPLETED: "Fix agent execution so traces complete",
    DeterministicCheck.EXPECTED_TOOLS_CALLED: (
        "Update the agent prompt or tool policy so expected tools are called"
    ),
    DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED: (
        "Add a guardrail before forbidden or destructive tool calls"
    ),
    DeterministicCheck.REQUIRED_TOOL_ARGS_MATCHED: (
        "Validate required tool arguments before execution"
    ),
    DeterministicCheck.MAX_STEPS_NOT_EXCEEDED: "Add loop limits or stop conditions",
    DeterministicCheck.FINAL_OUTPUT_EXISTS: "Ensure the agent produces a final response",
    DeterministicCheck.CLARIFYING_QUESTION_ASKED: (
        "Ask for missing identity or lookup information before proceeding"
    ),
}


class FailureCluster(BaseModel):
    name: str
    count: int
    severity: str
    examples: list[str]
    repair_plan: list[str] = Field(default_factory=list)


def cluster_failures(failures: list[GradeResult]) -> list[FailureCluster]:
    grouped: dict[tuple[str, str], list[GradeResult]] = defaultdict(list)
    for failure in failures:
        key = _failure_key(failure)
        grouped[key].append(failure)

    clusters = [
        FailureCluster(
            name=name,
            count=len(items),
            severity=severity,
            examples=[f"{item.scenario_id}/trial_{item.trial}" for item in items[:5]],
            repair_plan=_repair_plan(items),
        )
        for (name, severity), items in grouped.items()
    ]
    return sorted(clusters, key=lambda cluster: (-cluster.count, cluster.severity, cluster.name))


def _repair_plan(items: list[GradeResult]) -> list[str]:
    seen: set[str] = set()
    plan: list[str] = []
    for item in items:
        has_semantic_patch = False
        for patch in item.semantic.suggested_fix.values():
            if patch:
                has_semantic_patch = True
            if patch and patch not in seen:
                seen.add(patch)
                plan.append(patch)
        if not item.semantic.passed and has_semantic_patch:
            continue
        for check in _failed_deterministic_checks(item):
            patch = _deterministic_repair(check)
            if patch not in seen:
                seen.add(patch)
                plan.append(patch)
    return plan


def _failure_key(failure: GradeResult) -> tuple[str, str]:
    if failure.semantic.failure_type != "none":
        return failure.semantic.failure_type, failure.semantic.severity

    failed_checks = _failed_deterministic_checks(failure)
    if failed_checks:
        check = failed_checks[0]
        return check.name.value, DETERMINISTIC_SEVERITY[check.name]

    return "unknown_failure", "medium"


def _failed_deterministic_checks(failure: GradeResult) -> list[CheckOutcome]:
    return [check for check in failure.deterministic_checks if not check.passed]


def _deterministic_repair(check: CheckOutcome) -> str:
    return f"{DETERMINISTIC_REPAIR_PREFIX[check.name]}: {check.reason}"
