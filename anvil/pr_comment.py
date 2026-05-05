from __future__ import annotations

from pathlib import Path

from anvil.clustering import FailureCluster
from anvil.grading import GradeResult
from anvil.storage import load_results


def write_pr_comment(run_dir: str | Path, *, out_path: str | Path) -> Path:
    comment = generate_pr_comment(run_dir)
    selected_out = Path(out_path)
    selected_out.parent.mkdir(parents=True, exist_ok=True)
    selected_out.write_text(comment, encoding="utf-8")
    return selected_out


def generate_pr_comment(run_dir: str | Path) -> str:
    payload = load_results(run_dir)
    grades = [GradeResult.model_validate(item) for item in payload["grades"]]
    clusters = [FailureCluster.model_validate(item) for item in payload["clusters"]]
    summary = payload["summary"]
    failed = [grade for grade in grades if not grade.passed]
    lines = [
        "## Agent Anvil PR Review",
        "",
        f"Suite: `{payload['suite']}`",
        f"Pass rate: **{summary['pass_rate']:.1f}%**",
        "",
    ]
    if not failed:
        lines.extend(
            [
                "No agent regressions detected.",
                "",
                "Trace artifacts are still available for review.",
            ]
        )
        return "\n".join(lines) + "\n"

    top_cluster = clusters[0] if clusters else None
    lines.append("### New agent regression")
    if top_cluster:
        lines.extend(
            [
                f"- Failure: `{top_cluster.name} / {top_cluster.severity}`",
                f"- Count: {top_cluster.count}",
                f"- Examples: {', '.join(top_cluster.examples)}",
            ]
        )
        if top_cluster.repair_plan:
            lines.append("- Suggested repair:")
            lines.extend(f"  - {item}" for item in top_cluster.repair_plan[:3])
    lines.extend(["", "### First failing trace"])
    first = failed[0]
    lines.extend(
        [
            f"- Scenario: `{first.scenario_id}/trial_{first.trial}`",
            f"- Trace: `{_display_trace_path(first.trace_path)}`",
            "",
            "This is a workflow regression: inspect tool choice, arguments, and ordering, not just "
            "the final answer.",
        ]
    )
    return "\n".join(lines) + "\n"


def _display_trace_path(trace_path: str) -> str:
    if "traces" in trace_path:
        return "runs/latest/traces/" + Path(trace_path).name
    return trace_path
