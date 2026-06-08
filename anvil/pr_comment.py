from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from anvil.clustering import FailureCluster
from anvil.grading import GradeResult
from anvil.storage import load_results


def write_pr_comment(
    run_dir: str | Path,
    *,
    out_path: str | Path,
    compare_path: str | Path | None = None,
) -> Path:
    comment = generate_pr_comment(run_dir, compare_path=compare_path)
    selected_out = Path(out_path)
    selected_out.parent.mkdir(parents=True, exist_ok=True)
    selected_out.write_text(comment, encoding="utf-8")
    return selected_out


def generate_pr_comment(run_dir: str | Path, *, compare_path: str | Path | None = None) -> str:
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
    compare_lines = _compare_delta_lines(compare_path)
    if compare_lines:
        lines.extend(["### Compared with baseline"])
        lines.extend(compare_lines)
        lines.append("")

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
    flaky_lines = _flaky_scenario_lines(summary.get("flaky_scenarios", []))
    if flaky_lines:
        lines.extend(["", "### Flaky scenarios"])
        lines.extend(flaky_lines)
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


def _compare_delta_lines(compare_path: str | Path | None) -> list[str]:
    if compare_path is None:
        return []
    selected_compare_path = Path(compare_path)
    try:
        payload = json.loads(selected_compare_path.read_text(encoding="utf-8"))
    except OSError:
        return _compare_unavailable_lines(selected_compare_path, "could not be read")
    except json.JSONDecodeError:
        return _compare_unavailable_lines(selected_compare_path, "could not be parsed as JSON")
    if not isinstance(payload, dict):
        return _compare_unavailable_lines(selected_compare_path, "did not contain a JSON object")

    compare = cast(dict[str, object], payload)
    lines: list[str] = []
    baseline_rate = _number(compare.get("baseline_pass_rate"))
    latest_rate = _number(compare.get("latest_pass_rate"))
    delta = _number(compare.get("delta"))
    if baseline_rate is not None and latest_rate is not None and delta is not None:
        lines.append(f"Pass rate: **{baseline_rate:.1f}% -> {latest_rate:.1f}% ({delta:+.1f}%)**")

    lines.extend(_failure_delta_lines("New failure", compare.get("new_failures")))
    lines.extend(_failure_delta_lines("Resolved failure", compare.get("resolved_failures")))
    lines.extend(_scenario_delta_lines("Regressed scenario", compare.get("scenario_regressions")))
    lines.extend(_scenario_delta_lines("Improved scenario", compare.get("scenario_improvements")))
    lines.extend(_flaky_delta_lines("Newly flaky", compare.get("new_flaky_scenarios")))
    lines.extend(_flaky_delta_lines("Stabilized", compare.get("resolved_flaky_scenarios")))
    return lines


def _compare_unavailable_lines(compare_path: Path, reason: str) -> list[str]:
    return [f"- Compare artifact unavailable: `{compare_path}` {reason}."]


def _failure_delta_lines(label: str, items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    lines: list[str] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        payload = cast(dict[str, object], item)
        failure_type = payload.get("failure_type")
        severity = payload.get("severity")
        baseline_count = payload.get("baseline_count")
        latest_count = payload.get("latest_count")
        if not (
            isinstance(failure_type, str)
            and isinstance(severity, str)
            and isinstance(baseline_count, int)
            and isinstance(latest_count, int)
        ):
            continue
        lines.append(f"- {label}: `{failure_type} / {severity}` {baseline_count} -> {latest_count}")
    return lines


def _scenario_delta_lines(label: str, items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    lines: list[str] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        payload = cast(dict[str, object], item)
        scenario_id = payload.get("scenario_id")
        baseline_rate = _number(payload.get("baseline_pass_rate"))
        latest_rate = _number(payload.get("latest_pass_rate"))
        if not (
            isinstance(scenario_id, str) and baseline_rate is not None and latest_rate is not None
        ):
            continue
        lines.append(f"- {label}: `{scenario_id}` {baseline_rate:.1f}% -> {latest_rate:.1f}%")
    return lines


def _flaky_delta_lines(label: str, items: object) -> list[str]:
    if not isinstance(items, list):
        return []

    lines: list[str] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        payload = cast(dict[str, object], item)
        scenario_id = payload.get("scenario_id")
        passed_trials = payload.get("passed_trials")
        total_trials = payload.get("total_trials")
        pass_rate = payload.get("pass_rate")
        if not (
            isinstance(scenario_id, str)
            and isinstance(passed_trials, int)
            and isinstance(total_trials, int)
            and isinstance(pass_rate, int | float)
        ):
            continue
        lines.append(
            f"- {label}: `{scenario_id}` {passed_trials}/{total_trials} "
            f"trials passed ({float(pass_rate):.1f}%)"
        )
    return lines


def _flaky_scenario_lines(flaky_scenarios: object) -> list[str]:
    if not isinstance(flaky_scenarios, list):
        return []

    lines: list[str] = []
    for item in flaky_scenarios:
        if not isinstance(item, dict):
            continue
        payload = cast(dict[str, object], item)
        scenario_id = payload.get("scenario_id")
        passed_trials = payload.get("passed_trials")
        total_trials = payload.get("total_trials")
        pass_rate = payload.get("pass_rate")
        if not (
            isinstance(scenario_id, str)
            and isinstance(passed_trials, int)
            and isinstance(total_trials, int)
            and isinstance(pass_rate, int | float)
        ):
            continue
        pass_rate_value = float(pass_rate)
        lines.append(
            f"- `{scenario_id}`: {passed_trials}/{total_trials} "
            f"trials passed ({pass_rate_value:.1f}%)"
        )
    return lines


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
