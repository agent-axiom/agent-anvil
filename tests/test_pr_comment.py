from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.grading import HeuristicSemanticGrader
from anvil.pr_comment import generate_pr_comment, write_pr_comment
from anvil.runner import run_suite


def test_generate_pr_comment_highlights_top_failure(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )

    comment = generate_pr_comment(result.run_dir)

    assert "## Agent Anvil PR Review" in comment
    assert "New agent regression" in comment
    assert "premature_tool_execution / high" in comment
    assert "refund_missing_order_id/trial_1" in comment
    assert "runs/latest/traces" in comment


def test_write_pr_comment_and_cli(tmp_path: Path, scenario_file: Path) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )
    out = tmp_path / "comment.md"

    path = write_pr_comment(result.run_dir, out_path=out)
    cli_result = CliRunner().invoke(app, ["pr-comment", str(result.run_dir), "--out", str(out)])

    assert path == out
    assert out.exists()
    assert cli_result.exit_code == 0
    assert f"Wrote {out}" in cli_result.stdout
