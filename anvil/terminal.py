from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from rich import box
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from anvil.grading import GradeResult
    from anvil.runner import RunResult

PERFECT_PASS_RATE = 100.0
WARNING_PASS_RATE = 80.0


def print_run_summary(result: RunResult, *, command: str | None = None) -> None:
    console = Console(width=110)
    console.print(render_run_summary(result, command=command))


def render_run_summary(result: RunResult, *, command: str | None = None) -> RenderableType:
    top_cluster = result.clusters[0] if result.clusters else None
    status = "PASS" if result.pass_rate == PERFECT_PASS_RATE else "REGRESSION CAUGHT BEFORE MERGE"
    status_style = "bold green" if result.pass_rate == PERFECT_PASS_RATE else "bold yellow"

    body = Group(
        _command_panel(result, command) if command else "",
        "",
        _summary_table(result, status=status, status_style=status_style),
        "",
        _result_row(result) if top_cluster else _scenario_panel(result.grades),
        "",
        _repair_panel(result) if top_cluster else _artifact_panel(result),
        "",
        Text("Final-answer evals miss this. Trace evals catch unsafe agent behavior.", style="dim"),
        "",
        Text("Run: " + str(result.run_dir), style="dim"),
        Text(f"Trials: {result.total_trials}", style="dim"),
        Text(f"Pass rate: {result.pass_rate:.1f}%", style="dim"),
    )
    return Panel(
        body,
        title="[bold]Agent Anvil eval report[/bold]",
        subtitle="trace-first CI harness",
        border_style="#334155",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _command_panel(result: RunResult, command: str) -> Panel:
    label = (
        "passing smoke test"
        if result.pass_rate == PERFECT_PASS_RATE
        else "intentional regression demo"
    )
    command_lines: list[RenderableType] = [
        Text(line, style="#93c5fd") for line in _command_lines(command)
    ]
    if result.pass_rate < PERFECT_PASS_RATE:
        command_lines.append(Text("$ uv run anvil repair runs/latest", style="#93c5fd"))
    command_lines.append(Align(Text(label, style="#fbbf24"), align="right"))
    return Panel(Group(*command_lines), border_style="#1e293b", box=box.ROUNDED, padding=(0, 2))


def _command_lines(command: str) -> list[str]:
    if " --" not in command:
        return [f"$ {command}"]
    head, _, flags = command.partition(" --")
    return [f"$ {head} \\", f"  --{flags}"]


def _summary_table(result: RunResult, *, status: str, status_style: str) -> Table:
    table = Table.grid(expand=True)
    table.add_column(ratio=2)
    table.add_column(ratio=1)
    table.add_column(ratio=1)
    table.add_column(ratio=3)
    table.add_row(
        _metric("Suite", _short_suite_name(result.suite_name)),
        _metric("Trials", str(result.total_trials)),
        _metric("Pass rate", f"{result.pass_rate:.1f}%", value_style=_pass_rate_style(result)),
        _metric("Status", status.lower(), value_style=status_style),
    )
    return table


def _result_row(result: RunResult) -> Table:
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=1)
    table.add_row(_scenario_panel(result.grades), _failure_panel(result))
    return table


def _scenario_panel(grades: list[GradeResult]) -> Panel:
    table = Table(
        box=None,
        show_header=False,
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Status", width=8)
    table.add_column("Scenario")
    for scenario_id, passed in _ordered_scenario_results(grades):
        label = "PASS" if passed else "FAIL"
        style = "bold green" if passed else "bold red"
        table.add_row(Text(label, style=style), scenario_id)
    return Panel(
        Group(Text("Scenario results", style="bold white"), "", table),
        border_style="#273449",
        box=box.ROUNDED,
        padding=(0, 2),
    )


def _failure_panel(result: RunResult) -> Panel:
    cluster = result.clusters[0]
    first_failure = next(grade for grade in result.grades if not grade.passed)
    lines = [
        Text("Top failure cluster", style="bold #fecaca"),
        Text(f"{cluster.name} / {cluster.severity}", style="#fca5a5"),
        Text(_failure_reason(first_failure), style="white"),
    ]
    argument_line = _tool_argument_line(first_failure)
    if argument_line:
        lines.append(Text(argument_line, style="white"))
    return Panel(Group(*lines), border_style="#ef4444", box=box.ROUNDED, padding=(0, 2))


def _repair_panel(result: RunResult) -> Table:
    cluster = result.clusters[0]
    table = Table.grid(expand=True)
    table.add_column(ratio=2)
    table.add_column(ratio=1)

    repair_lines = [Text("Repair plan", style="bold #bbf7d0")]
    if cluster.repair_plan:
        labels = ["Prompt", "Tool"]
        repair_lines.extend(
            Text(f"{label}: {item}")
            for label, item in zip(labels, cluster.repair_plan[:2], strict=False)
        )
    else:
        repair_lines.append(Text("Prompt: review trace and deterministic checks."))
    repair_lines.append(Text("uv run anvil repair runs/latest", style="#5eead4"))

    artifacts = Group(
        Text("Artifacts", style="bold"),
        Text(str(_latest_artifact_path(result, "report.md"))),
        Text(str(_latest_artifact_path(result, "results.json"))),
        Text(str(_latest_artifact_path(result, "traces"))),
    )
    table.add_row(
        Panel(Group(*repair_lines), border_style="#22c55e", box=box.ROUNDED, padding=(0, 2)),
        Panel(artifacts, border_style="#273449", box=box.ROUNDED, padding=(0, 2)),
    )
    return table


def _success_panel() -> Panel:
    return Panel(
        Text("No failure clusters. The suite passed all trials.", style="bold green"),
        border_style="#22c55e",
        box=box.ROUNDED,
        padding=(0, 2),
    )


def _artifact_panel(result: RunResult) -> Panel:
    artifacts = Group(
        Text("Artifacts", style="bold"),
        Text(str(_latest_artifact_path(result, "report.md"))),
        Text(str(_latest_artifact_path(result, "results.json"))),
        Text(str(_latest_artifact_path(result, "traces"))),
    )
    return Panel(artifacts, border_style="#273449", box=box.ROUNDED, padding=(0, 2))


def _metric(
    label: str,
    value: str,
    *,
    value_style: str = "bold white",
) -> Panel:
    return Panel(
        Group(Text(label, style="dim"), Text(value, style=value_style)),
        border_style="#273449",
        box=box.ROUNDED,
        padding=(0, 2),
    )


def _scenario_results(grades: list[GradeResult]) -> dict[str, bool]:
    grouped: dict[str, list[GradeResult]] = defaultdict(list)
    for grade in grades:
        grouped[grade.scenario_id].append(grade)
    return {
        scenario_id: all(grade.passed for grade in scenario_grades)
        for scenario_id, scenario_grades in sorted(grouped.items())
    }


def _ordered_scenario_results(grades: list[GradeResult]) -> list[tuple[str, bool]]:
    return sorted(_scenario_results(grades).items(), key=lambda item: (not item[1], item[0]))


def _pass_rate_style(result: RunResult) -> str:
    if result.pass_rate == PERFECT_PASS_RATE:
        return "bold green"
    if result.pass_rate >= WARNING_PASS_RATE:
        return "bold yellow"
    return "bold red"


def _short_suite_name(suite_name: str) -> str:
    return suite_name.removesuffix("_regression_suite")


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def _latest_artifact_path(result: RunResult, name: str) -> Path:
    return _display_path(result.run_dir.parent / "latest" / name)


def _failure_reason(grade: GradeResult) -> str:
    reason = grade.semantic.reason or "Review trace and deterministic checks."
    if grade.semantic.failure_type == "premature_tool_execution" and "issue_refund" in reason:
        return "issue_refund called before order verification"
    return reason


def _tool_argument_line(grade: GradeResult) -> str:
    try:
        payload = json.loads(Path(grade.trace_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as _error:
        return ""

    for step in payload.get("steps", []):
        if step.get("type") != "tool_call":
            continue
        if step.get("tool_name") != "issue_refund":
            continue
        arguments = step.get("arguments")
        if isinstance(arguments, dict) and "order_id" in arguments:
            return f'argument: order_id="{arguments["order_id"]}"'
    return ""
