from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from anvil.grading import GradeResult
    from anvil.runner import RunResult

PERFECT_PASS_RATE = 100.0
WARNING_PASS_RATE = 80.0


def print_run_summary(result: RunResult) -> None:
    console = Console(width=110)
    console.print(render_run_summary(result))


def render_run_summary(result: RunResult) -> RenderableType:
    top_cluster = result.clusters[0] if result.clusters else None
    status = "PASS" if result.pass_rate == PERFECT_PASS_RATE else "REGRESSION CAUGHT"
    status_style = "bold green" if result.pass_rate == PERFECT_PASS_RATE else "bold yellow"

    body = Group(
        _summary_table(result, status=status, status_style=status_style),
        "",
        _scenario_table(result.grades),
        "",
        _failure_panel(result) if top_cluster else _success_panel(),
        "",
        _repair_panel(result) if top_cluster else _artifact_panel(result),
        "",
        Text("Run: " + str(result.run_dir), style="dim"),
        Text(f"Trials: {result.total_trials}", style="dim"),
        Text(f"Pass rate: {result.pass_rate:.1f}%", style="dim"),
    )
    return Panel(
        body,
        title="[bold]Agent Anvil eval report[/bold]",
        subtitle="trace-first CI harness",
        border_style="slate_blue1",
        box=box.ROUNDED,
        padding=(1, 2),
    )


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


def _scenario_table(grades: list[GradeResult]) -> Table:
    table = Table(
        title="Scenario results",
        box=box.SIMPLE,
        show_header=False,
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Status", width=10)
    table.add_column("Scenario")
    for scenario_id, passed in _scenario_results(grades).items():
        label = "PASS" if passed else "FAIL"
        style = "bold green" if passed else "bold red"
        table.add_row(Text(label, style=style), scenario_id)
    return table


def _failure_panel(result: RunResult) -> Panel:
    cluster = result.clusters[0]
    first_failure = next(grade for grade in result.grades if not grade.passed)
    lines = [
        Text("Top failure cluster", style="bold red"),
        Text(f"{cluster.name} / {cluster.severity}", style="red"),
        Text(first_failure.semantic.reason or "Review trace and deterministic checks."),
    ]
    if cluster.examples:
        lines.append(Text("examples: " + ", ".join(cluster.examples[:3]), style="dim"))
    return Panel(Group(*lines), border_style="red", box=box.ROUNDED)


def _repair_panel(result: RunResult) -> Table:
    cluster = result.clusters[0]
    table = Table.grid(expand=True)
    table.add_column(ratio=2)
    table.add_column(ratio=1)

    repair_lines = [Text("Repair hint", style="bold green")]
    if cluster.repair_plan:
        repair_lines.extend(Text(f"- {item}") for item in cluster.repair_plan[:2])
    else:
        repair_lines.append(Text("- Run the repair command and inspect traces."))
    repair_lines.append(Text("uv run anvil repair runs/latest", style="cyan"))

    artifacts = Group(
        Text("Artifacts", style="bold"),
        Text(str(_latest_artifact_path(result, "report.md"))),
        Text(str(_latest_artifact_path(result, "results.json"))),
        Text(str(_latest_artifact_path(result, "traces"))),
    )
    table.add_row(Panel(Group(*repair_lines), border_style="green"), Panel(artifacts))
    return table


def _success_panel() -> Panel:
    return Panel(
        Text("No failure clusters. The suite passed all trials.", style="bold green"),
        border_style="green",
        box=box.ROUNDED,
    )


def _artifact_panel(result: RunResult) -> Panel:
    artifacts = Group(
        Text("Artifacts", style="bold"),
        Text(str(_latest_artifact_path(result, "report.md"))),
        Text(str(_latest_artifact_path(result, "results.json"))),
        Text(str(_latest_artifact_path(result, "traces"))),
    )
    return Panel(artifacts, border_style="slate_blue1", box=box.ROUNDED)


def _metric(
    label: str,
    value: str,
    *,
    value_style: str = "bold white",
) -> Panel:
    return Panel(
        Group(Text(label, style="dim"), Text(value, style=value_style)),
        border_style="grey23",
        box=box.ROUNDED,
    )


def _scenario_results(grades: list[GradeResult]) -> dict[str, bool]:
    grouped: dict[str, list[GradeResult]] = defaultdict(list)
    for grade in grades:
        grouped[grade.scenario_id].append(grade)
    return {
        scenario_id: all(grade.passed for grade in scenario_grades)
        for scenario_id, scenario_grades in sorted(grouped.items())
    }


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
