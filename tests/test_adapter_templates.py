from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anvil.cli import app
from anvil.external import emit_final_output, emit_model_call, emit_tool_call, read_payload


def test_adapter_list_mentions_supported_frameworks() -> None:
    result = CliRunner().invoke(app, ["adapter", "list"])

    assert result.exit_code == 0
    assert "openai-agents" in result.output
    assert "langgraph" in result.output


def test_adapter_add_writes_openai_agents_template(tmp_path: Path) -> None:
    out_path = tmp_path / "openai_agents_adapter.py"

    result = CliRunner().invoke(app, ["adapter", "add", "openai-agents", "--out", str(out_path)])

    assert result.exit_code == 0
    assert "Wrote adapter template:" in result.output
    content = out_path.read_text(encoding="utf-8")
    compile(content, str(out_path), "exec")
    assert "def handle_anvil(payload: dict[str, Any]) -> dict[str, Any]:" in content
    assert 'ANVIL_OPENAI_AGENTS_MODE", "offline"' in content
    assert 'function_tool(name_override="lookup_order")' in content
    assert "agents.Runner.run_sync" in content
    assert "def create_fastapi_app() -> Any:" in content
    assert "emit_final_output" in content
    assert "Agent Anvil adapter starter for OpenAI Agents SDK" in content


def test_generated_openai_agents_template_runs_offline_jsonl(tmp_path: Path) -> None:
    out_path = tmp_path / "openai_agents_adapter.py"
    result = CliRunner().invoke(app, ["adapter", "add", "openai-agents", "--out", str(out_path)])
    assert result.exit_code == 0

    completed = subprocess.run(
        [sys.executable, str(out_path)],
        input=json.dumps(
            {
                "scenario_id": "generated_openai_agents",
                "input": "Please check order ORD-123 before issuing any refund.",
                "trial": 1,
                "run_id": "run_test",
                "max_steps": 8,
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "ANVIL_OPENAI_AGENTS_MODE": "offline"},
    )

    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert events[0]["type"] == "model_call"
    assert events[0]["model"] == "openai-agents-sdk-offline-demo"
    assert events[1] == {
        "type": "tool_call",
        "tool_name": "lookup_order",
        "arguments": {"order_id": "ORD-123"},
        "result": {"order_id": "ORD-123", "status": "found", "verified": True},
    }
    assert events[-1]["type"] == "final_output"


def test_adapter_add_writes_langgraph_template(tmp_path: Path) -> None:
    out_path = tmp_path / "langgraph_adapter.py"

    result = CliRunner().invoke(app, ["adapter", "add", "langgraph", "--out", str(out_path)])

    assert result.exit_code == 0
    content = out_path.read_text(encoding="utf-8")
    compile(content, str(out_path), "exec")
    assert "from langgraph.graph import END, START, StateGraph" in content
    assert "graph.invoke" in content
    assert "emit_tool_call" in content
    assert "Agent Anvil external JSONL adapter for LangGraph" in content


def test_adapter_add_refuses_overwrite_without_force(tmp_path: Path) -> None:
    out_path = tmp_path / "adapter.py"
    out_path.write_text("existing\n", encoding="utf-8")

    blocked = CliRunner().invoke(app, ["adapter", "add", "langgraph", "--out", str(out_path)])

    assert blocked.exit_code == 1
    assert "already exists" in blocked.output
    assert out_path.read_text(encoding="utf-8") == "existing\n"

    forced = CliRunner().invoke(
        app,
        ["adapter", "add", "langgraph", "--out", str(out_path), "--force"],
    )

    assert forced.exit_code == 0
    assert "StateGraph" in out_path.read_text(encoding="utf-8")


def test_adapter_add_rejects_unknown_template(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["adapter", "add", "unknown-framework", "--out", str(tmp_path / "adapter.py")],
    )

    assert result.exit_code == 1
    assert "Unknown adapter template" in result.output
    assert "openai-agents" in result.output
    assert "langgraph" in result.output


def test_external_helper_emits_protocol_jsonl_events() -> None:
    payload = read_payload(stdin=io.StringIO('{"scenario_id":"s1","input":"hello"}'))
    stdout = io.StringIO()

    emit_model_call(
        model="adapter-test",
        input_text=payload["input"],
        output_text="planning",
        tool_calls=[{"name": "lookup", "arguments": {"id": "1"}}],
        stdout=stdout,
    )
    emit_tool_call(
        tool_name="lookup",
        arguments={"id": "1"},
        result={"status": "ok"},
        stdout=stdout,
    )
    emit_final_output("done", stdout=stdout)

    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert events == [
        {
            "type": "model_call",
            "model": "adapter-test",
            "input": "hello",
            "output_text": "planning",
            "tool_calls": [{"name": "lookup", "arguments": {"id": "1"}}],
        },
        {
            "type": "tool_call",
            "tool_name": "lookup",
            "arguments": {"id": "1"},
            "result": {"status": "ok"},
        },
        {"type": "final_output", "text": "done"},
    ]


def test_external_helper_rejects_non_object_stdin_payload() -> None:
    with pytest.raises(TypeError, match="stdin payload must be a JSON object"):
        read_payload(stdin=io.StringIO('["not", "an", "object"]'))
