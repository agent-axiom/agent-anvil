from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.scenario import ExternalAgentConfig, load_scenario_file


def test_pack_list_shows_builtin_tool_safety_pack() -> None:
    result = CliRunner().invoke(app, ["pack", "list"])

    assert result.exit_code == 0
    assert "tool-safety" in result.stdout
    assert "destructive tool" in result.stdout


def test_pack_add_writes_tool_safety_scenario(tmp_path: Path) -> None:
    out = tmp_path / "scenarios" / "tool_safety.yaml"

    result = CliRunner().invoke(
        app,
        [
            "pack",
            "add",
            "tool-safety",
            "--agent-command",
            "python my_agent.py",
            "--out",
            str(out),
        ],
    )

    suite = load_scenario_file(out)
    text = out.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "Wrote" in result.stdout
    assert suite.name == "tool_safety_starter_suite"
    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.command == "python my_agent.py"
    assert suite.policies.destructive_tools == [
        "delete_project",
        "issue_refund",
        "send_email",
        "transfer_money",
    ]
    assert {scenario.id for scenario in suite.scenarios} >= {
        "destructive_tool_requires_verification",
        "hallucinated_identifier_is_blocked",
        "tool_error_requires_recovery",
    }
    assert "require_before:" in text


def test_pack_add_refuses_unknown_pack(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "pack",
            "add",
            "unknown-pack",
            "--agent-command",
            "python my_agent.py",
            "--out",
            str(tmp_path / "scenario.yaml"),
        ],
    )

    assert result.exit_code == 1
    assert "Unknown pack" in result.stderr


def test_pack_add_customizes_tool_safety_tools(tmp_path: Path) -> None:
    out = tmp_path / "scenarios" / "custom_tool_safety.yaml"

    result = CliRunner().invoke(
        app,
        [
            "pack",
            "add",
            "tool-safety",
            "--agent-command",
            "python my_agent.py",
            "--risky-tool",
            "issue_refund",
            "--risky-tool",
            "delete_workspace",
            "--verification-tool",
            "lookup_order",
            "--approval-required-tool",
            "delete_workspace",
            "--out",
            str(out),
        ],
    )

    suite = load_scenario_file(out)
    text = out.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert suite.policies.destructive_tools == ["issue_refund", "delete_workspace"]
    assert suite.policies.require_human_approval == ["delete_workspace"]
    assert sorted(suite.policies.require_before) == ["delete_workspace", "issue_refund"]
    assert suite.policies.require_before["issue_refund"][0].tool == "lookup_order"
    assert "delete_project" not in text
    assert "transfer_money" not in text


def test_init_can_include_tool_safety_pack(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--agent-command",
            "python my_agent.py",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
            "--pack",
            "tool-safety",
        ],
    )

    suite = load_scenario_file(scenario_path)
    assert result.exit_code == 0
    assert suite.name == "tool_safety_starter_suite"
    assert "delete_project" in suite.policies.destructive_tools


def test_init_can_customize_tool_safety_pack(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--agent-command",
            "python my_agent.py",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
            "--pack",
            "tool-safety",
            "--risky-tool",
            "send_wire",
            "--verification-tool",
            "verify_account",
            "--approval-required-tool",
            "send_wire",
        ],
    )

    suite = load_scenario_file(scenario_path)
    assert result.exit_code == 0
    assert suite.policies.destructive_tools == ["send_wire"]
    assert suite.policies.require_before["send_wire"][0].tool == "verify_account"
    assert suite.policies.require_human_approval == ["send_wire"]


def test_init_ci_safe_profile_writes_adapter_pack_and_pr_workflow(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            app,
            [
                "init",
                "--profile",
                "ci-safe",
                "--scenario",
                "scenarios/starter.yaml",
                "--workflow",
                ".github/workflows/agent-anvil.yml",
                "--risky-tool",
                "issue_refund",
                "--verification-tool",
                "lookup_order",
            ],
        )

        suite = load_scenario_file(Path("scenarios/starter.yaml"))
        workflow_text = Path(".github/workflows/agent-anvil.yml").read_text(encoding="utf-8")
        adapter_path = Path("adapters/http_python_adapter.py")
        assert result.exit_code == 0
        assert adapter_path.exists()
        assert suite.name == "tool_safety_starter_suite"
        assert isinstance(suite.agent, ExternalAgentConfig)
        assert suite.agent.command == "python adapters/http_python_adapter.py"
        assert suite.policies.destructive_tools == ["issue_refund"]
        assert suite.policies.require_before["issue_refund"][0].tool == "lookup_order"
        assert "pull-requests: write" in workflow_text
        assert 'post-pr-comment: "true"' in workflow_text


def test_init_ci_safe_profile_can_use_existing_agent_command(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--profile",
            "ci-safe",
            "--agent-command",
            "python my_agent.py",
            "--scenario",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    suite = load_scenario_file(scenario_path)
    assert result.exit_code == 0
    assert suite.name == "tool_safety_starter_suite"
    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.command == "python my_agent.py"


def test_init_rejects_unknown_profile(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--profile",
            "unknown",
            "--agent-command",
            "python my_agent.py",
            "--scenario",
            str(tmp_path / "scenario.yaml"),
            "--workflow",
            str(tmp_path / "workflow.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "Unknown init profile" in result.stderr


def test_init_ci_safe_profile_rejects_http_agent(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--profile",
            "ci-safe",
            "--agent-url",
            "http://127.0.0.1:8080/anvil",
            "--scenario",
            str(tmp_path / "scenario.yaml"),
            "--workflow",
            str(tmp_path / "workflow.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "ci-safe profile requires a JSONL agent command or adapter" in result.stderr
