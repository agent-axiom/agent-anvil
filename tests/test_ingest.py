from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.ingest import ingest_jsonl_trace
from anvil.trace import TraceRun


def test_ingest_jsonl_writes_anvil_trace(tmp_path: Path) -> None:
    source = tmp_path / "agent_failure.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "model_call",
                        "model": "gpt-5.4-mini",
                        "input": "refund missing order",
                        "output_text": "I will issue the refund.",
                    }
                ),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "issue_refund",
                        "arguments": {"order_id": "UNKNOWN"},
                        "result": {"status": "ok"},
                    }
                ),
                json.dumps({"type": "final_output", "text": "Refund issued."}),
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "imported-prod"

    trace_path = ingest_jsonl_trace(
        source,
        out_dir=out_dir,
        scenario_id="prod_refund_failure_001",
        user_input="I want a refund but lost my order ID",
    )

    trace = TraceRun.model_validate_json(trace_path.read_text(encoding="utf-8"))
    assert trace_path == out_dir / "traces" / "prod_refund_failure_001_trial_1.json"
    assert trace.scenario_id == "prod_refund_failure_001"
    assert trace.input == "I want a refund but lost my order ID"
    assert trace.status == "completed"
    assert trace.final_output == "Refund issued."
    assert trace.steps[1]["tool_name"] == "issue_refund"


def test_cli_ingest_jsonl_writes_trace(tmp_path: Path) -> None:
    source = tmp_path / "agent_failure.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps({"type": "model_call", "output_text": "Need a tool."}),
                json.dumps({"type": "final_output", "text": "done"}),
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "imported"

    result = CliRunner().invoke(
        app,
        [
            "ingest",
            "jsonl",
            str(source),
            "--scenario-id",
            "prod_case",
            "--input",
            "hello",
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Wrote" in result.stdout
    assert (out_dir / "traces" / "prod_case_trial_1.json").exists()


def test_ingest_jsonl_reports_malformed_json(tmp_path: Path) -> None:
    source = tmp_path / "bad.jsonl"
    source.write_text('{"type": "model_call"}\nnot-json\n', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "ingest",
            "jsonl",
            str(source),
            "--scenario-id",
            "bad_case",
            "--input",
            "hello",
            "--out",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1
    assert "Malformed JSONL on line 2" in result.stderr


def test_ingest_jsonl_requires_final_output(tmp_path: Path) -> None:
    source = tmp_path / "missing_final.jsonl"
    source.write_text(json.dumps({"type": "model_call", "output_text": "hello"}), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "ingest",
            "jsonl",
            str(source),
            "--scenario-id",
            "missing_final",
            "--input",
            "hello",
            "--out",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1
    assert "JSONL trace must include a final_output event" in result.stderr
