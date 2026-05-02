from __future__ import annotations

from pathlib import Path

import typer

from anvil.repair import generate_repair_plan
from anvil.runner import compare_runs, default_semantic_grader, regenerate_report, run_suite

app = typer.Typer(help="Agent Anvil CI-first eval harness.")
PASSING_RATE = 100.0
TRIALS_OPTION = typer.Option(None, "--trials", min=1, help="Override trial count.")
RUNS_DIR_OPTION = typer.Option(Path("runs"), "--runs-dir", help="Run artifact directory.")
OFFLINE_OPTION = typer.Option(False, "--offline", help="Use local heuristic grading only.")
AGENT_MODE_OPTION = typer.Option(
    None,
    "--agent-mode",
    help="Agent execution mode for demo agents: offline, openai, or auto.",
)


@app.command()
def run(
    scenario_file: Path,
    trials: int | None = TRIALS_OPTION,
    runs_dir: Path = RUNS_DIR_OPTION,
    offline: bool = OFFLINE_OPTION,
    agent_mode: str | None = AGENT_MODE_OPTION,
) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=runs_dir,
        trials_override=trials,
        semantic_grader=default_semantic_grader(offline=offline),
        agent_mode=agent_mode,
    )
    typer.echo(f"Run: {result.run_dir}")
    typer.echo(f"Trials: {result.total_trials}")
    typer.echo(f"Pass rate: {result.pass_rate:.1f}%")
    if result.pass_rate < PASSING_RATE:
        raise typer.Exit(1)


@app.command()
def report(run_dir: Path) -> None:
    report_path = regenerate_report(run_dir)
    typer.echo(f"Regenerated {report_path}")


@app.command()
def repair(run_dir: Path) -> None:
    repair_path = generate_repair_plan(run_dir)
    typer.echo(f"Wrote {repair_path}")


@app.command()
def compare(baseline_dir: Path, latest_dir: Path) -> None:
    result = compare_runs(baseline_dir, latest_dir)
    typer.echo(f"Baseline pass rate: {result['baseline_pass_rate']:.1f}%")
    typer.echo(f"Latest pass rate: {result['latest_pass_rate']:.1f}%")
    typer.echo(f"Delta: {result['delta']:+.1f}%")


if __name__ == "__main__":
    app()
