from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from anvil.grading import GradeResult


class FailureCluster(BaseModel):
    name: str
    count: int
    severity: str
    examples: list[str]
    repair_plan: list[str] = Field(default_factory=list)


def cluster_failures(failures: list[GradeResult]) -> list[FailureCluster]:
    grouped: dict[tuple[str, str], list[GradeResult]] = defaultdict(list)
    for failure in failures:
        key = (failure.semantic.failure_type, failure.semantic.severity)
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
        for patch in item.semantic.suggested_fix.values():
            if patch and patch not in seen:
                seen.add(patch)
                plan.append(patch)
    return plan
