from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.clustering import cluster_failures
from anvil.grading import (
    CheckOutcome,
    DeterministicCheck,
    GradeResult,
    HeuristicSemanticGrader,
    SemanticGrade,
)
from anvil.repair import generate_repair_plan, render_repair_plan
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


def test_render_repair_plan_uses_deterministic_failure_when_semantic_passed() -> None:
    grade = GradeResult(
        scenario_id="refund_missing_order_id",
        trial=1,
        passed=False,
        deterministic_passed=False,
        semantic=SemanticGrade(
            passed=True,
            score=1.0,
            suggested_fix={
                "prompt_patch": "",
                "tool_description_patch": "",
                "guardrail_patch": "",
            },
        ),
        trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
        deterministic_checks=[
            CheckOutcome(
                name=DeterministicCheck.EXPECTED_TOOLS_CALLED,
                passed=False,
                reason="missing expected tool calls: lookup_customer",
            )
        ],
    )

    text = render_repair_plan(
        suite_name="refund_agent_regression_suite",
        run_id="run_test",
        grades=[grade],
        clusters=cluster_failures([grade]),
    )

    assert "Failure type: expected_tools_called" in text
    assert "Severity: medium" in text
    assert "Reason: missing expected tool calls: lookup_customer" in text
    assert "Failure type: none" not in text
    assert "prompt_patch:" not in text


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
