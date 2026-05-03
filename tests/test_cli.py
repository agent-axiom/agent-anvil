from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app


def test_cli_requires_explicit_offline_without_openai_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANVIL_OFFLINE", raising=False)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "scenarios/external_jsonl_agent.yaml",
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 2
    assert "OPENAI_API_KEY is required for OpenAI semantic grading" in result.stderr
    assert "--offline" in result.stderr


def test_cli_run_writes_artifacts_and_returns_failure_for_failed_suite(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runner = CliRunner()

    result = runner.invoke(
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

    assert result.exit_code == 1
    assert "Agent Anvil eval report" in result.stdout
    assert "$ uv run anvil run" in result.stdout
    assert "--offline" in result.stdout
    assert "--trials 1" in result.stdout
    assert "intentional regression demo" in result.stdout
    assert "Scenario results" in result.stdout
    assert "Top failure cluster" in result.stdout
    assert "Repair plan" in result.stdout
    assert "uv run anvil repair runs/latest" in result.stdout
    assert "Pass rate: 50.0%" in result.stdout
    assert (runs_dir / "latest" / "results.json").exists()


def test_cli_report_regenerates_markdown_from_results(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runner = CliRunner()
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

    report_result = runner.invoke(app, ["report", str(runs_dir / "latest")])

    assert report_result.exit_code == 0
    assert "Regenerated" in report_result.stdout
    assert "# Agent Anvil Report" in (runs_dir / "latest" / "report.md").read_text(encoding="utf-8")


def test_cli_summary_prints_github_summary(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runner = CliRunner()
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

    summary_result = runner.invoke(app, ["summary", str(runs_dir / "latest"), "--github"])

    assert summary_result.exit_code == 0
    assert "## Agent Anvil Summary" in summary_result.stdout
    assert "| Pass rate | 50.0% |" in summary_result.stdout
    assert "premature_tool_execution" in summary_result.stdout


def test_cli_compare_reports_pass_rate_regression(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    baseline_dir = tmp_path / "baseline"
    latest_dir = tmp_path / "latest"
    runner.invoke(
        app,
        [
            "run",
            str(scenario_file),
            "--runs-dir",
            str(baseline_dir),
            "--trials",
            "1",
            "--offline",
        ],
    )
    runner.invoke(
        app,
        [
            "run",
            str(scenario_file),
            "--runs-dir",
            str(latest_dir),
            "--trials",
            "2",
            "--offline",
        ],
    )

    compare_result = runner.invoke(
        app,
        ["compare", str(baseline_dir / "latest"), str(latest_dir / "latest")],
    )

    assert compare_result.exit_code == 0
    assert "Baseline pass rate: 50.0%" in compare_result.stdout
    assert "Latest pass rate: 50.0%" in compare_result.stdout


def test_cli_compare_reports_resolved_failures(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    baseline_dir = tmp_path / "baseline"
    latest_dir = tmp_path / "latest"
    runner.invoke(
        app,
        [
            "run",
            str(scenario_file),
            "--runs-dir",
            str(baseline_dir),
            "--trials",
            "1",
            "--offline",
        ],
    )
    runner.invoke(
        app,
        [
            "run",
            "scenarios/refund_agent_patched.yaml",
            "--runs-dir",
            str(latest_dir),
            "--trials",
            "1",
            "--offline",
        ],
    )

    compare_result = runner.invoke(
        app,
        ["compare", str(baseline_dir / "latest"), str(latest_dir / "latest")],
    )

    assert compare_result.exit_code == 0
    assert "Latest pass rate: 100.0%" in compare_result.stdout
    assert "Resolved failures:" in compare_result.stdout
    assert "- premature_tool_execution / high: 1 -> 0" in compare_result.stdout


def test_cli_compare_reports_new_failures_and_scenario_regressions(tmp_path: Path) -> None:
    runner = CliRunner()
    baseline_dir = tmp_path / "baseline"
    latest_dir = tmp_path / "latest"
    runner.invoke(
        app,
        [
            "run",
            "scenarios/refund_agent_patched.yaml",
            "--runs-dir",
            str(baseline_dir),
            "--trials",
            "1",
            "--offline",
        ],
    )
    runner.invoke(
        app,
        [
            "run",
            "scenarios/refund_agent.yaml",
            "--runs-dir",
            str(latest_dir),
            "--trials",
            "1",
            "--offline",
            "--agent-mode",
            "offline",
        ],
    )

    compare_result = runner.invoke(
        app,
        ["compare", str(baseline_dir / "latest"), str(latest_dir / "latest")],
    )

    assert compare_result.exit_code == 0
    assert "New failures:" in compare_result.stdout
    assert "- premature_tool_execution / high: 0 -> 1" in compare_result.stdout
    assert "Scenario regressions:" in compare_result.stdout
    assert "- refund_missing_order_id: 100.0% -> 0.0% (-100.0%)" in compare_result.stdout
