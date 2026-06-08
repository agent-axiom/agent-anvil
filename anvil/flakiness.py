from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from anvil.grading import GradeResult


@dataclass(frozen=True)
class FlakyScenario:
    scenario_id: str
    passed_trials: int
    failed_trials: int
    total_trials: int
    pass_rate: float

    def to_json(self) -> dict[str, int | float | str]:
        return asdict(self)


def detect_flaky_scenarios(grades: list[GradeResult]) -> list[FlakyScenario]:
    grouped: dict[str, list[GradeResult]] = defaultdict(list)
    for grade in grades:
        grouped[grade.scenario_id].append(grade)

    flaky: list[FlakyScenario] = []
    for scenario_id, scenario_grades in sorted(grouped.items()):
        passed_trials = sum(1 for grade in scenario_grades if grade.passed)
        total_trials = len(scenario_grades)
        if not 0 < passed_trials < total_trials:
            continue
        failed_trials = total_trials - passed_trials
        flaky.append(
            FlakyScenario(
                scenario_id=scenario_id,
                passed_trials=passed_trials,
                failed_trials=failed_trials,
                total_trials=total_trials,
                pass_rate=round(passed_trials / total_trials * 100, 1),
            )
        )
    return flaky
