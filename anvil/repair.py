from __future__ import annotations

from pathlib import Path

from anvil.clustering import FailureCluster
from anvil.grading import GradeResult
from anvil.storage import load_results


def generate_repair_plan(run_dir: str | Path) -> Path:
    payload = load_results(run_dir)
    grades = [GradeResult.model_validate(item) for item in payload["grades"]]
    clusters = [FailureCluster.model_validate(item) for item in payload["clusters"]]
    repair_plan = render_repair_plan(
        suite_name=str(payload["suite"]),
        run_id=str(payload["run_id"]),
        grades=grades,
        clusters=clusters,
    )
    repair_path = Path(run_dir) / "repair_plan.md"
    repair_path.write_text(repair_plan, encoding="utf-8")
    return repair_path


def render_repair_plan(
    *,
    suite_name: str,
    run_id: str,
    grades: list[GradeResult],
    clusters: list[FailureCluster],
) -> str:
    failed = [grade for grade in grades if not grade.passed]
    lines = [
        "# Agent Anvil Repair Plan",
        "",
        f"Suite: {suite_name}",
        f"Run: {run_id}",
        f"Failed trials: {len(failed)}",
        "",
    ]

    if not failed:
        lines.extend(["No failing trials found.", ""])
        return "\n".join(lines)

    lines.append("## Prioritized Fixes")
    if clusters:
        for index, cluster in enumerate(clusters, start=1):
            lines.extend(
                [
                    f"{index}. {cluster.name}",
                    f"   Severity: {cluster.severity}",
                    f"   Count: {cluster.count}",
                    "   Repair plan:",
                ]
            )
            if cluster.repair_plan:
                lines.extend(f"   - {item}" for item in cluster.repair_plan)
            else:
                lines.append("   - Inspect traces and add a narrower scenario expectation.")
    else:
        lines.append("1. Review failed deterministic checks and semantic reasons.")

    lines.extend(["", "## Failed Trials"])
    for grade in failed:
        lines.extend(
            [
                f"- {grade.scenario_id}/trial_{grade.trial}",
                f"  Failure type: {grade.semantic.failure_type}",
                f"  Severity: {grade.semantic.severity}",
                f"  Reason: {grade.semantic.reason or 'No semantic reason supplied.'}",
            ]
        )
        for patch_type, patch in grade.semantic.suggested_fix.items():
            lines.append(f"  {patch_type}: {patch}")
        failing_checks = [check for check in grade.deterministic_checks if not check.passed]
        lines.extend(
            f"  Deterministic check: {check.name} - {check.reason}" for check in failing_checks
        )
        lines.append(f"  Trace: {grade.trace_path}")

    return "\n".join(lines) + "\n"
