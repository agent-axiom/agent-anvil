from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from anvil.cli import app
from anvil.mcp_audit import audit_mcp_tools
from anvil.scenario import load_scenario_file


def _tools_payload() -> list[dict[str, object]]:
    return [
        {
            "name": "delete_project",
            "description": "Deletes a project.",
            "input_schema": {
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
            },
        },
        {
            "name": "lookup_project",
            "description": "Looks up and verifies a project before destructive actions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier, supplied by the user.",
                    }
                },
            },
        },
    ]


def test_audit_mcp_tools_generates_safety_scenarios_and_report(tmp_path: Path) -> None:
    out = tmp_path / "mcp_tool_safety.yaml"
    report = tmp_path / "mcp-audit.md"

    result = audit_mcp_tools(_tools_payload(), out_path=out, report_path=report)

    assert result.risky_tool_count == 1
    assert out.exists()
    assert report.exists()
    suite = load_scenario_file(out)
    assert suite.policies.destructive_tools == ["delete_project"]
    assert suite.policies.require_human_approval == ["delete_project"]
    assert suite.scenarios[0].expected.should_not_call_tools == ["delete_project"]
    assert "missing_preconditions" in report.read_text(encoding="utf-8")
    assert "missing argument description: project_id" in report.read_text(encoding="utf-8")


def test_cli_mcp_audit_writes_artifacts(tmp_path: Path) -> None:
    tools_json = tmp_path / "tools.json"
    tools_json.write_text(json.dumps(_tools_payload()), encoding="utf-8")
    out = tmp_path / "mcp_tool_safety.yaml"
    report = tmp_path / "mcp-audit.md"

    result = CliRunner().invoke(
        app,
        ["mcp", "audit", str(tools_json), "--out", str(out), "--report", str(report)],
    )

    assert result.exit_code == 0
    assert f"Wrote {out}" in result.stdout
    assert f"Wrote {report}" in result.stdout
    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert payload["name"] == "mcp_tool_safety_suite"
