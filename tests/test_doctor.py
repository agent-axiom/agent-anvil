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


def test_doctor_passes_for_marketplace_action_workflow(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    _write_workflow(
        workflow_path,
        scenario_path=scenario_path,
        action_ref="agent-axiom/agent-anvil-action@v1.0.7",
    )

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
    assert "- github_workflow: PASS" in result.stdout


def test_doctor_rejects_stale_marketplace_action_ref(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    _write_workflow(
        workflow_path,
        scenario_path=scenario_path,
        action_ref="agent-axiom/agent-anvil-action@v1.0.1",
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    assert result.exit_code == 1
    assert "- github_workflow: FAIL" in result.stdout
    assert "workflow uses stale Agent Anvil Marketplace action ref v1.0.1" in result.stdout
    assert "agent-axiom/agent-anvil-action@v1.0.7" in result.stdout
    assert "agent-axiom/agent-anvil-action@v1" in result.stdout


def test_doctor_allows_marketplace_action_major_ref(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    _write_workflow(
        workflow_path,
        scenario_path=scenario_path,
        action_ref="agent-axiom/agent-anvil-action@v1",
    )

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
    assert "- github_workflow: PASS" in result.stdout


def test_doctor_rejects_pr_comment_workflow_without_pull_request_write_permission(
    tmp_path: Path,
) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        f"""name: Agent Anvil
permissions:
  contents: read
jobs:
  agent-anvil:
    steps:
      - uses: actions/checkout@v6
      - uses: agent-axiom/agent-anvil-action@v1.0.7
        with:
          scenario: {scenario_path.as_posix()}
          post-pr-comment: "true"
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    assert result.exit_code == 1
    assert "- github_workflow: FAIL" in result.stdout
    assert "post-pr-comment requires pull-requests: write" in result.stdout
    assert "permissions:" in result.stdout


def test_doctor_allows_pr_comment_workflow_with_pull_request_write_permission(
    tmp_path: Path,
) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        f"""name: Agent Anvil
permissions:
  contents: read
  pull-requests: write
jobs:
  agent-anvil:
    steps:
      - uses: actions/checkout@v6
      - uses: agent-axiom/agent-anvil-action@v1.0.7
        with:
          scenario: {scenario_path.as_posix()}
          post-pr-comment: "true"
""",
        encoding="utf-8",
    )

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
    assert "- github_workflow: PASS" in result.stdout


def test_doctor_rejects_workflow_without_checkout_before_agent_anvil_action(
    tmp_path: Path,
) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        f"""name: Agent Anvil
jobs:
  agent-anvil:
    steps:
      - uses: agent-axiom/agent-anvil-action@v1.0.7
        with:
          scenario: {scenario_path.as_posix()}
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    assert result.exit_code == 1
    assert "- github_workflow: FAIL" in result.stdout
    assert "workflow should check out the repository before Agent Anvil runs" in result.stdout
    assert "actions/checkout" in result.stdout


def test_doctor_rejects_workflow_with_action_only_in_comments(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        f"""name: Agent Anvil
# uses: agent-axiom/agent-anvil-action@v1.0.7
# scenario: {scenario_path.as_posix()}
jobs:
  agent-anvil:
    steps:
      - uses: actions/checkout@v6
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--workflow",
            str(workflow_path),
        ],
    )

    assert result.exit_code == 1
    assert "- github_workflow: FAIL" in result.stdout
    assert "workflow does not contain an Agent Anvil action step" in result.stdout


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
    assert "Hint:" in result.stdout
    assert "uv run anvil init --profile ci-safe" in result.stdout


def test_doctor_can_skip_workflow_check_for_local_diagnostics(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--skip-workflow",
        ],
    )

    assert result.exit_code == 0
    assert "Agent Anvil doctor: PASS" in result.stdout
    assert "- scenario_file: PASS" in result.stdout
    assert "- external_agent_conformance: PASS" in result.stdout
    assert "github_workflow" not in result.stdout


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


def test_doctor_json_includes_failure_hints(tmp_path: Path) -> None:
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
            "--json",
        ],
    )

    payload = json.loads(result.stdout)
    workflow_check = next(
        check for check in payload["checks"] if check["name"] == "github_workflow"
    )
    assert result.exit_code == 1
    assert workflow_check["passed"] is False
    assert "uv run anvil init --profile ci-safe" in workflow_check["hint"]


def test_doctor_skip_workflow_json_omits_workflow_check(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    _write_jsonl_scenario(
        scenario_path, command=f"{sys.executable} fixtures/conformance/pass_agent.py"
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(scenario_path),
            "--skip-workflow",
            "--json",
        ],
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["passed"] is True
    assert {check["name"] for check in payload["checks"]} == {
        "scenario_file",
        "agent_target",
        "external_agent_conformance",
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


def test_doctor_appends_github_step_summary(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    workflow_path = tmp_path / ".github" / "workflows" / "agent-anvil.yml"
    summary_path = tmp_path / "github-summary.md"
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
            "--github-summary",
        ],
        env={"GITHUB_STEP_SUMMARY": str(summary_path)},
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "# Agent Anvil Doctor" in summary
    assert "Status: PASS" in summary
    assert "| scenario_file | PASS |" in summary
    assert "| github_workflow | PASS |" in summary


def test_doctor_github_step_summary_includes_failure_hints(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "starter.yaml"
    summary_path = tmp_path / "github-summary.md"
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
            "--github-summary",
        ],
        env={"GITHUB_STEP_SUMMARY": str(summary_path)},
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert result.exit_code == 1
    assert "Status: FAIL" in summary
    assert "uv run anvil init --profile ci-safe" in summary


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


def _write_workflow(
    path: Path,
    *,
    scenario_path: Path,
    action_ref: str = "agent-axiom/agent-anvil@v0.2.18",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""name: Agent Anvil
jobs:
  agent-anvil:
    steps:
      - uses: actions/checkout@v6
      - uses: {action_ref}
        with:
          scenario: {scenario_path.as_posix()}
""",
        encoding="utf-8",
    )
