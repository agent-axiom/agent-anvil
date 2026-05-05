from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from anvil.cli import app
from anvil.mcp_audit import audit_mcp_tools, snapshot_mcp_tools
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


def test_snapshot_mcp_tools_writes_tools_from_stdio_server(tmp_path: Path) -> None:
    server = _write_fake_mcp_server(tmp_path)
    out = tmp_path / "mcp-tools.json"

    tools = snapshot_mcp_tools(f"{sys.executable} {server}", out_path=out)

    assert tools[0]["name"] == "delete_project"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["tools"][0]["name"] == "delete_project"


def test_cli_mcp_snapshot_can_audit_snapshot(tmp_path: Path) -> None:
    server = _write_fake_mcp_server(tmp_path)
    snapshot = tmp_path / "mcp-tools.json"
    scenario = tmp_path / "mcp_tool_safety.yaml"
    report = tmp_path / "mcp-audit.md"

    result = CliRunner().invoke(
        app,
        [
            "mcp",
            "snapshot",
            "--command",
            f"{sys.executable} {server}",
            "--out",
            str(snapshot),
            "--audit-out",
            str(scenario),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote {snapshot}" in result.stdout
    assert f"Wrote {scenario}" in result.stdout
    assert f"Wrote {report}" in result.stdout
    assert load_scenario_file(scenario).policies.destructive_tools == ["delete_project"]


def _write_fake_mcp_server(tmp_path: Path) -> Path:
    server = tmp_path / "fake_mcp_server.py"
    server.write_text(
        r"""
from __future__ import annotations

import json
import sys


TOOLS = [
    {
        "name": "delete_project",
        "description": "Deletes a project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
        },
    }
]


def read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line == b"\r\n":
            break
        key, value = line.decode("ascii").strip().split(":", 1)
        headers[key.lower()] = value.strip()
    body = sys.stdin.buffer.read(int(headers["content-length"]))
    return json.loads(body)


def write_message(payload):
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    if method == "initialize":
        write_message({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
            },
        })
    elif method == "tools/list":
        write_message({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": TOOLS}})
        break
""",
        encoding="utf-8",
    )
    return server
