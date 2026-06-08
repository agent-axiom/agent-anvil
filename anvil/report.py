from __future__ import annotations

from collections import defaultdict

from anvil.clustering import FailureCluster
from anvil.flakiness import FlakyScenario, detect_flaky_scenarios
from anvil.grading import GradeResult


def render_markdown_report(
    *,
    suite_name: str,
    run_id: str,
    total_scenarios: int,
    grades: list[GradeResult],
    clusters: list[FailureCluster],
) -> str:
    total_trials = len(grades)
    passed_trials = sum(1 for grade in grades if grade.passed)
    pass_rate = (passed_trials / total_trials * 100) if total_trials else 0.0

    lines = [
        "# Agent Anvil Report",
        "",
        f"Suite: {suite_name}",
        f"Run: {run_id}",
        f"Total scenarios: {total_scenarios}",
        f"Trials: {total_trials}",
        f"Pass rate: {pass_rate:.1f}%",
        "",
        "## Top failure clusters",
    ]

    if clusters:
        for index, cluster in enumerate(clusters, start=1):
            lines.extend(
                [
                    f"{index}. {cluster.name}",
                    f"   Count: {cluster.count}",
                    f"   Severity: {cluster.severity}",
                    "   Suggested fix:",
                ]
            )
            if cluster.repair_plan:
                lines.extend(f"   - {item}" for item in cluster.repair_plan)
            else:
                lines.append("   - Review trace and deterministic checks.")
    else:
        lines.append("No failures clustered.")

    lines.extend(["", "## Scenario results"])
    scenario_results = _scenario_results(grades)
    for scenario_id, passed in scenario_results.items():
        status = "PASS" if passed else "FAIL"
        lines.append(f"- {scenario_id}: {status}")

    flaky_scenarios = _flaky_scenario_results(grades)
    if flaky_scenarios:
        lines.extend(["", "## Flaky scenarios"])
        lines.extend(
            (
                f"- {scenario.scenario_id}: {scenario.passed_trials}/{scenario.total_trials} "
                f"trials passed ({scenario.pass_rate:.1f}%)"
            )
            for scenario in flaky_scenarios
        )

    lines.extend(["", "## Trace examples"])
    lines.extend(f"- {grade.trace_path}" for grade in grades[:10])

    return "\n".join(lines) + "\n"


def render_github_summary(
    *,
    suite_name: str,
    run_id: str,
    total_scenarios: int,
    grades: list[GradeResult],
    clusters: list[FailureCluster],
) -> str:
    total_trials = len(grades)
    passed_trials = sum(1 for grade in grades if grade.passed)
    failed_trials = total_trials - passed_trials
    pass_rate = (passed_trials / total_trials * 100) if total_trials else 0.0
    status = "PASS" if failed_trials == 0 else "FAIL"

    lines = [
        "## Agent Anvil Summary",
        "",
        f"**Status:** {status}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Suite | {suite_name} |",
        f"| Run | {run_id} |",
        f"| Total scenarios | {total_scenarios} |",
        f"| Trials | {total_trials} |",
        f"| Passed trials | {passed_trials} |",
        f"| Failed trials | {failed_trials} |",
        f"| Pass rate | {pass_rate:.1f}% |",
        "",
        "### Failure Clusters",
    ]

    if clusters:
        lines.extend(["", "| Failure type | Severity | Count |", "| --- | --- | --- |"])
        lines.extend(
            f"| {cluster.name} | {cluster.severity} | {cluster.count} |" for cluster in clusters
        )
        lines.extend(["", "### Suggested Fixes"])
        for cluster in clusters:
            lines.append(f"- `{cluster.name}`")
            if cluster.repair_plan:
                lines.extend(f"  - {item}" for item in cluster.repair_plan)
            else:
                lines.append("  - Review trace and deterministic checks.")
    else:
        lines.append("")
        lines.append("No failure clusters.")

    failed = [grade for grade in grades if not grade.passed]
    if failed:
        lines.extend(["", "### Failed Trials"])
        lines.extend(
            f"- `{grade.scenario_id}/trial_{grade.trial}`: "
            f"{grade.semantic.failure_type} ({grade.semantic.severity})"
            for grade in failed
        )

    flaky_scenarios = _flaky_scenario_results(grades)
    if flaky_scenarios:
        lines.extend(["", "### Flaky Scenarios"])
        lines.extend(
            (
                f"- `{scenario.scenario_id}`: {scenario.passed_trials}/{scenario.total_trials} "
                f"trials passed ({scenario.pass_rate:.1f}%)"
            )
            for scenario in flaky_scenarios
        )

    lines.extend(
        [
            "",
            "### Artifacts",
            "- `report.md`",
            "- `results.json`",
            "- `manifest.json`",
            "- `traces/*.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def _scenario_results(grades: list[GradeResult]) -> dict[str, bool]:
    grouped: dict[str, list[GradeResult]] = defaultdict(list)
    for grade in grades:
        grouped[grade.scenario_id].append(grade)
    return {
        scenario_id: all(grade.passed for grade in scenario_grades)
        for scenario_id, scenario_grades in sorted(grouped.items())
    }


def _flaky_scenario_results(grades: list[GradeResult]) -> list[FlakyScenario]:
    return detect_flaky_scenarios(grades)
