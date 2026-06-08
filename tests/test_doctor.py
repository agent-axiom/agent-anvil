from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app


def test_doctor_passes_for_valid_jsonl_scenario_and_workflow(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    _write_workflow(workflow_path, scenario_path=scenario_path)

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    assert result.exit_code == 0
    assert "Agent Anvil doctor: PASS" in result.stdout
    assert "- scenario_file: PASS" in result.stdout
    assert "- external_agent_conformance: PASS" in result.stdout
    assert "- github_workflow: PASS" in result.stdout


def test_doctor_fails_when_workflow_is_missing(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(tmp_path / ".github" / "workflows" / "agent-anvil.yml"),
        ],
    )

    assert result.exit_code == 1
    assert "Agent Anvil doctor: FAIL" in result.stdout
    assert "- scenario_file: PASS" in result.stdout
    assert "- external_agent_conformance: PASS" in result.stdout
    assert "- github_workflow: FAIL" in result.stdout
    assert "workflow file does not exist" in result.stdout


def test_doctor_fails_for_invalid_scenario_yaml(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "broken.yaml"
    scenario_path.parent.mkdir(parents=True)
    scenario_path.write_text("name: [broken\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["doctor", str(scenario_path)])

    assert result.exit_code == 1
    assert "Agent Anvil doctor: FAIL" in result.stdout
    assert "- scenario_file: FAIL" in result.stdout
    assert "could not load scenario" in result.stdout
    assert "external_agent_conformance" not in result.stdout


def test_doctor_can_print_json_report(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    _write_workflow(workflow_path, scenario_path=scenario_path)

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
            "--json",
        ],
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["passed"] is True
    assert payload["checks"][0] == {
        "name": "scenario_file",
        "passed": True,
        "message": f"loaded {scenario_path.as_posix()}",
    }
    assert {check["name"] for check in payload["checks"]} == {
        "scenario_file",
        "agent_target",
        "external_agent_conformance",
        "github_workflow",
    }


def test_doctor_writes_json_report_to_out_path(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    out_path = tmp_path / "reports" / "doctor.json"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    _write_workflow(workflow_path, scenario_path=scenario_path)

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
            "--out",
            str(out_path),
        ],
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert "Agent Anvil doctor: PASS" in result.stdout
    assert "Wrote doctor report:" in result.stdout
    assert payload["passed"] is True
    assert payload["checks"][-1]["name"] == "github_workflow"


def _write_jsonl_scenario(path: Path, *, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""name: doctor_test_suite
agent:
  command: "{command}"
  protocol: jsonl
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: doctor_smoke
    input: "Check conformance."
    expected:
      success_criteria:
        - "Agent emits a final output"
""",
        encoding="utf-8",
    )


def _write_workflow(path: Path, *, scenario_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""name: Agent Anvil
jobs:
  agent-anvil:
    steps:
      - uses: agent-axiom/agent-anvil@v0.2.18
        with:
          scenario: {scenario_path.as_posix()}
""",
        encoding="utf-8",
    )
