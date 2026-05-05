from __future__ import annotations

from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from anvil.cli import app
from anvil.mcp_repair import (
    McpRepairPatch,
    McpRepairPlan,
    OpenAIMcpRepairer,
    generate_mcp_repair,
)


def _tools_payload() -> list[dict[str, object]]:
    return [
        {
            "name": "delete_project",
            "description": "Deletes a project.",
            "inputSchema": {
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
            },
        }
    ]


def test_generate_mcp_repair_writes_offline_tool_description_and_policy_plan(
    tmp_path: Path,
) -> None:
    report = tmp_path / "mcp-repair.md"

    result = generate_mcp_repair(_tools_payload(), out_path=report, offline=True)

    assert result.report_path == report
    assert result.plan.patches[0].tool_name == "delete_project"
    content = report.read_text(encoding="utf-8")
    assert "Only call `delete_project` after verification" in content
    assert "Add a required prior verification policy for `delete_project`" in content
    assert "Document `project_id`" in content


def test_cli_mcp_repair_writes_report(tmp_path: Path) -> None:
    tools_file = tmp_path / "tools.json"
    tools_file.write_text(
        """
{
  "tools": [
    {
      "name": "delete_project",
      "description": "Deletes a project.",
      "inputSchema": {
        "type": "object",
        "properties": {"project_id": {"type": "string"}}
      }
    }
  ]
}
""",
        encoding="utf-8",
    )
    report = tmp_path / "mcp-repair.md"

    result = CliRunner().invoke(
        app,
        ["mcp", "repair", str(tools_file), "--out", str(report), "--offline"],
    )

    assert result.exit_code == 0
    assert f"Wrote {report}" in result.stdout
    assert "## Tool description patches" in report.read_text(encoding="utf-8")


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object):
        self.calls.append(kwargs)

        class ParsedResponse:
            output_parsed = McpRepairPlan(
                summary="MCP tools need explicit safety preconditions.",
                patches=[
                    McpRepairPatch(
                        tool_name="delete_project",
                        current_description="Deletes a project.",
                        suggested_description=(
                            "Only call delete_project after lookup_project verifies the project "
                            "exists, belongs to the current tenant, and human approval is present."
                        ),
                        rationale="Destructive MCP tools need explicit preconditions.",
                        policy_patch=[
                            "Add delete_project to destructive_tools.",
                            "Require lookup_project before delete_project.",
                        ],
                        scenario_patch=[
                            "Add a scenario where delete_project is requested without approval."
                        ],
                    )
                ],
            )

        return ParsedResponse()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_mcp_repairer_uses_structured_schema_and_redacts_payload() -> None:
    client = FakeClient()
    repairer = OpenAIMcpRepairer(client=client, model="gpt-5.5")
    tools = [
        {
            "name": "delete_project",
            "description": "Deletes project tenant-1234 for alice@example.com.",
            "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}},
        }
    ]

    plan = repairer.repair(tools)

    assert plan.patches[0].tool_name == "delete_project"
    assert client.responses.calls[0]["model"] == "gpt-5.5"
    assert client.responses.calls[0]["text_format"] is McpRepairPlan
    input_messages = cast(list[dict[str, str]], client.responses.calls[0]["input"])
    payload = input_messages[1]["content"]
    assert "alice@example.com" not in payload
    assert "tenant-1234" not in payload
    assert "[REDACTED_EMAIL]" in payload
