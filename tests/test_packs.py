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
