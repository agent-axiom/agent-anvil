from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.scenario import ExternalAgentConfig, load_scenario_file


def test_cli_init_writes_starter_scenario_and_workflow(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "init",
            "--agent-command",
            "python my_agent.py",
            "--scenario",
            str(tmp_path / "scenarios" / "starter.yaml"),
            "--workflow",
            str(tmp_path / ".github" / "workflows" / "agent-anvil.yml"),
            "--post-pr-comment",
        ],
    )

    scenario_text = (tmp_path / "scenarios" / "starter.yaml").read_text(encoding="utf-8")
    workflow_text = (tmp_path / ".github" / "workflows" / "agent-anvil.yml").read_text(
        encoding="utf-8"
    )
    assert result.exit_code == 0
    assert "Wrote" in result.stdout
    assert 'command: "python my_agent.py"' in scenario_text
    assert "protocol: jsonl" in scenario_text
    assert "starter_tool_safety" in scenario_text
    assert "agent-axiom/agent-anvil@v" in workflow_text
    assert "pull-requests: write" in workflow_text
    assert 'post-pr-comment: "true"' in workflow_text


def test_cli_init_writes_http_starter_scenario_and_workflow(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--agent-url",
            "http://127.0.0.1:8080/anvil",
            "--header",
            "Authorization=Bearer $ANVIL_AGENT_TOKEN",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    suite = load_scenario_file(scenario_path)
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "Next: start your HTTP agent endpoint" in result.stdout
    assert "anvil conformance external-agent --url" in result.stdout
    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.protocol == "http"
    assert suite.agent.url == "http://127.0.0.1:8080/anvil"
    assert suite.agent.headers == {"Authorization": "Bearer $ANVIL_AGENT_TOKEN"}
    assert "Run HTTP agent conformance" in workflow_text
    assert "uvx --from git+https://github.com/agent-axiom/agent-anvil@v" in workflow_text
    assert "ANVIL_AGENT_TOKEN: ${{ secrets.ANVIL_AGENT_TOKEN }}" in workflow_text
    assert "anvil conformance external-agent" in workflow_text
    assert '--url "http://127.0.0.1:8080/anvil"' in workflow_text
    assert '--header "Authorization=Bearer $ANVIL_AGENT_TOKEN"' in workflow_text
    assert "scenario: " + scenario_path.as_posix() in workflow_text


def test_cli_init_with_adapter_writes_adapter_scenario_and_workflow(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    adapter_path = tmp_path / "adapters" / "http_python_adapter.py"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--adapter",
            "http-python",
            "--adapter-out",
            str(adapter_path),
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    scenario_text = scenario_path.read_text(encoding="utf-8")
    adapter_text = adapter_path.read_text(encoding="utf-8")
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "Wrote" in result.stdout
    assert "Next: edit the generated adapter" in result.stdout
    assert "Agent Anvil stdlib HTTP adapter starter" in adapter_text
    assert f'command: "python {adapter_path.as_posix()}"' in scenario_text
    assert "protocol: jsonl" in scenario_text
    assert "scenario: " + scenario_path.as_posix() in workflow_text
    assert "Run Agent Anvil doctor" not in workflow_text


def test_cli_init_with_adapter_uses_default_adapter_path(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "init",
                "--adapter",
                "langgraph",
                "--scenario",
                "scenarios/starter.yaml",
                "--workflow",
                ".github/workflows/agent-anvil.yml",
            ],
        )

        adapter_path = Path("adapters/langgraph_adapter.py")
        scenario_text = Path("scenarios/starter.yaml").read_text(encoding="utf-8")
        assert result.exit_code == 0
        assert adapter_path.exists()
        assert f'command: "python {adapter_path.as_posix()}"' in scenario_text


def test_cli_init_rejects_ambiguous_agent_targets(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--agent-command",
            "python my_agent.py",
            "--agent-url",
            "http://127.0.0.1:8080/anvil",
            "--scenario",
            str(tmp_path / "scenario.yaml"),
            "--workflow",
            str(tmp_path / "workflow.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "Use only one of --agent-command, --agent-url, or --adapter" in result.stderr


def test_cli_init_rejects_adapter_with_agent_command(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--adapter",
            "http-python",
            "--agent-command",
            "python my_agent.py",
            "--scenario",
            str(tmp_path / "scenario.yaml"),
            "--workflow",
            str(tmp_path / "workflow.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "Use only one of --agent-command, --agent-url, or --adapter" in result.stderr


def test_cli_init_rejects_adapter_out_without_adapter(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--agent-command",
            "python my_agent.py",
            "--adapter-out",
            str(tmp_path / "adapters" / "agent.py"),
            "--scenario",
            str(tmp_path / "scenario.yaml"),
            "--workflow",
            str(tmp_path / "workflow.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "--adapter-out only applies to --adapter" in result.stderr


def test_cli_init_rejects_headers_without_http_agent(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--agent-command",
            "python my_agent.py",
            "--header",
            "Authorization=Bearer $ANVIL_AGENT_TOKEN",
            "--scenario",
            str(tmp_path / "scenario.yaml"),
            "--workflow",
            str(tmp_path / "workflow.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "--header only applies to --agent-url" in result.stderr


def test_cli_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    runner = CliRunner()
    first = runner.invoke(
        app,
        [
            "init",
            "--agent-command",
            "python old_agent.py",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )
    second = runner.invoke(
        app,
        [
            "init",
            "--agent-command",
            "python new_agent.py",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )
    forced = runner.invoke(
        app,
        [
            "init",
            "--agent-command",
            "python new_agent.py",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
            "--force",
        ],
    )

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "already exists" in second.stderr
    assert forced.exit_code == 0
    assert 'command: "python new_agent.py"' in scenario_path.read_text(encoding="utf-8")


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


def test_cli_bench_writes_benchmark_outputs(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "paper.yaml"
    json_path = tmp_path / "paper-results.json"
    markdown_path = tmp_path / "paper-results.md"
    manifest_path.write_text(
        f"""
name: paper_benchmark
suites:
  - {scenario_file}
output:
  json: {json_path}
  markdown: {markdown_path}
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "bench",
            str(manifest_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--offline",
        ],
    )

    assert result.exit_code == 0
    assert "Benchmark: paper_benchmark" in result.stdout
    assert "Final-answer baseline pass rate: 100.0% [95% CI: 61.0%, 100.0%]" in result.stdout
    assert "Trace-aware Agent Anvil pass rate: 50.0% [95% CI: 18.8%, 81.2%]" in result.stdout
    assert "Answer-only missed failures: 3" in result.stdout
    assert "Answer-only missed failure rate: 50.0% [95% CI: 18.8%, 81.2%]" in result.stdout
    assert json_path.exists()
    assert markdown_path.exists()


def test_cli_paper_reproduce_writes_artifact_bundle(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "paper.yaml"
    json_path = tmp_path / "paper" / "results.json"
    markdown_path = tmp_path / "paper" / "results.md"
    tables_path = tmp_path / "paper" / "tables"
    manifest_path.write_text(
        f"""
name: paper_benchmark
suites:
  - {scenario_file}
output:
  json: {json_path}
  markdown: {markdown_path}
  tables: {tables_path}
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "paper",
            "reproduce",
            "--manifest",
            str(manifest_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 0
    assert "Reproduced Agent Anvil paper artifacts" in result.stdout
    assert "Benchmark: paper_benchmark" in result.stdout
    assert "Final-answer baseline pass rate: 100.0% [95% CI: 61.0%, 100.0%]" in result.stdout
    assert "Trace-aware Agent Anvil pass rate: 50.0% [95% CI: 18.8%, 81.2%]" in result.stdout
    assert f"Results JSON: {json_path}" in result.stdout
    assert f"Results Markdown: {markdown_path}" in result.stdout
    assert f"Tables: {tables_path}" in result.stdout
    assert "Evaluator ablation:" in result.stdout
    assert json_path.exists()
    assert markdown_path.exists()
    assert (tables_path / "suite_results.csv").exists()
    assert (tables_path / "evaluator_ablation.csv").exists()


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
