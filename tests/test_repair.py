from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.grading import HeuristicSemanticGrader
from anvil.repair import generate_repair_plan
from anvil.runner import run_suite


def test_generate_repair_plan_from_failed_run(scenario_file: Path, tmp_path: Path) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )

    repair_path = generate_repair_plan(result.run_dir)

    text = repair_path.read_text(encoding="utf-8")
    assert "# Agent Anvil Repair Plan" in text
    assert "premature_tool_execution" in text
    assert "Block destructive tools when required identifiers are missing." in text


def test_cli_repair_writes_repair_plan(scenario_file: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    runs_dir = tmp_path / "runs"
    runner.invoke(
        app,
        [
            "run",
            str(scenario_file),
            "--runs-dir",
            str(runs_dir),
            "--trials",
            "1",
            "--offline",
        ],
    )

    repair_result = runner.invoke(app, ["repair", str(runs_dir / "latest")])

    assert repair_result.exit_code == 0
    assert "repair_plan.md" in repair_result.stdout
    assert (runs_dir / "latest" / "repair_plan.md").exists()
