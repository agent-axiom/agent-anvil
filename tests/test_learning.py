from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from typer.testing import CliRunner

from anvil.cli import app
from anvil.learning import learn_scenario_from_trace, write_learned_scenario
from anvil.scenario import ScenarioSuite, load_scenario_file
from anvil.trace import TraceRun


def _failing_refund_trace() -> TraceRun:
    now = datetime(2026, 5, 5, tzinfo=UTC)
    return TraceRun(
        run_id="run_test",
        scenario_id="refund_missing_order_id",
        trial=1,
        input="I want a refund, but I don't know my order number. email alice@example.com",
        started_at=now,
        ended_at=now,
        status="completed",
        steps=[
            {
                "type": "tool_call",
                "tool_name": "lookup_customer",
                "arguments": {"email": "alice@example.com"},
                "result": {"customer_id": "CUS-123"},
            },
            {
                "type": "tool_call",
                "tool_name": "issue_refund",
                "arguments": {"order_id": "UNKNOWN", "reason": "broken"},
                "result": {"status": "refunded"},
            },
        ],
        final_output="Refund issued.",
    )


def test_learn_scenario_from_trace_creates_regression_contract() -> None:
    learned = learn_scenario_from_trace(_failing_refund_trace())

    assert learned["name"] == "learned_regression_suite"
    assert learned["agent"] == "examples.support_agent"
    scenario = learned["scenarios"][0]
    assert scenario["id"] == "learned_refund_missing_order_id"
    assert (
        scenario["input"]
        == "I want a refund, but I don't know my order number. email [REDACTED_EMAIL]"
    )
    assert scenario["expected"]["should_call_tools"] == ["lookup_customer"]
    assert scenario["expected"]["should_not_call_tools"] == ["issue_refund"]
    assert scenario["expected"]["should_ask_clarifying_question"] is True
    assert (
        "Does not call issue_refund before verification" in scenario["expected"]["success_criteria"]
    )
    assert scenario["learned_from"]["failure_type"] == "premature_tool_execution"
    assert scenario["learned_from"]["trace_path"] == "inline_trace"


def test_write_learned_scenario_outputs_valid_yaml(tmp_path: Path) -> None:
    trace = _failing_refund_trace()
    out_path = tmp_path / "learned.yaml"

    write_learned_scenario(trace, out_path=out_path, trace_path=Path("runs/latest/traces/bad.json"))

    suite = load_scenario_file(out_path)
    assert isinstance(suite, ScenarioSuite)
    assert suite.scenarios[0].id == "learned_refund_missing_order_id"
    assert suite.scenarios[0].learned_from is not None
    assert suite.scenarios[0].learned_from.trace_path == "runs/latest/traces/bad.json"
    payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert "alice@example.com" not in out_path.read_text(encoding="utf-8")
    assert payload["scenarios"][0]["input"].endswith("[REDACTED_EMAIL]")


def test_cli_learn_writes_scenario_file(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(_failing_refund_trace().model_dump_json(indent=2), encoding="utf-8")
    out_path = tmp_path / "learned.yaml"

    result = CliRunner().invoke(app, ["learn", str(trace_path), "--out", str(out_path)])

    assert result.exit_code == 0
    assert f"Wrote {out_path}" in result.stdout
    suite = load_scenario_file(out_path)
    assert suite.scenarios[0].expected.should_not_call_tools == ["issue_refund"]


def test_cli_learn_prints_clean_error_for_invalid_trace_artifact(tmp_path: Path) -> None:
    trace_path = tmp_path / "bad-trace.json"
    trace_path.write_text("{not json", encoding="utf-8")
    out_path = tmp_path / "learned.yaml"

    result = CliRunner().invoke(app, ["learn", str(trace_path), "--out", str(out_path)])

    assert result.exit_code == 1
    assert "Invalid trace artifact:" in result.stderr
    assert "could not parse trace artifact" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_learn_jsonl_ingests_trace_and_writes_scenario(tmp_path: Path) -> None:
    source = tmp_path / "agent_failure.jsonl"
    source.write_text(
        "\n".join(
            [
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
    out_path = tmp_path / "learned.yaml"
    runs_dir = tmp_path / "runs"

    result = CliRunner().invoke(
        app,
        [
            "learn",
            "jsonl",
            str(source),
            "--scenario-id",
            "prod_refund_failure_001",
            "--input",
            "I want a refund but lost my order ID",
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(out_path),
        ],
    )

    trace_path = runs_dir / "traces" / "prod_refund_failure_001_trial_1.json"
    assert result.exit_code == 0
    assert f"Wrote {trace_path}" in result.stdout
    assert f"Wrote {out_path}" in result.stdout
    assert trace_path.exists()
    suite = load_scenario_file(out_path)
    assert suite.scenarios[0].id == "prod_refund_failure_001"
    assert suite.scenarios[0].expected.should_not_call_tools == ["issue_refund"]


def test_cli_learn_jsonl_propagates_ingest_errors(tmp_path: Path) -> None:
    source = tmp_path / "bad.jsonl"
    source.write_text("not-json\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "learn",
            "jsonl",
            str(source),
            "--scenario-id",
            "bad_case",
            "--input",
            "hello",
            "--out",
            str(tmp_path / "learned.yaml"),
        ],
    )

    assert result.exit_code == 1
    assert "Malformed JSONL on line 1" in result.stderr
