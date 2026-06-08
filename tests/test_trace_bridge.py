from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.storage import write_trace
from anvil.trace import TraceRun
from anvil.trace_bridge import export_openai_trace, import_openai_trace


def _trace() -> TraceRun:
    now = datetime(2026, 5, 5, tzinfo=UTC)
    return TraceRun(
        run_id="run_bridge",
        scenario_id="refund_valid_order",
        trial=1,
        input="Refund ORD-123",
        started_at=now,
        ended_at=now,
        status="completed",
        steps=[
            {
                "type": "model_call",
                "model": "gpt-5.4-mini",
                "input": "Refund ORD-123",
                "output_text": "I will look up the order.",
                "tool_calls": [{"name": "lookup_order"}],
            },
            {
                "type": "tool_call",
                "tool_name": "lookup_order",
                "arguments": {"order_id": "ORD-123"},
                "result": {"eligible_for_refund": True},
            },
        ],
        final_output="Order verified.",
    )


def test_export_openai_trace_maps_anvil_events(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "traces").mkdir(parents=True)
    write_trace(run_dir, _trace())
    out = tmp_path / "openai-trace.json"

    export_openai_trace(run_dir, out_path=out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["format"] == "openai-trace"
    assert payload["traces"][0]["events"][0]["type"] == "generation"
    assert payload["traces"][0]["events"][1]["type"] == "tool_call"
    assert payload["traces"][0]["events"][1]["name"] == "lookup_order"


def test_import_openai_trace_writes_anvil_trace(tmp_path: Path) -> None:
    source = tmp_path / "openai-trace.json"
    source.write_text(
        json.dumps(
            {
                "format": "openai-trace",
                "run_id": "run_imported",
                "traces": [
                    {
                        "scenario_id": "imported_case",
                        "trial": 1,
                        "input": "hello",
                        "final_output": "done",
                        "events": [
                            {
                                "type": "generation",
                                "model": "gpt-5.4-mini",
                                "output_text": "hello",
                            },
                            {
                                "type": "tool_call",
                                "name": "lookup_order",
                                "arguments": {"order_id": "ORD-123"},
                                "result": {"status": "found"},
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "imported"

    imported = import_openai_trace(source, out_dir=out_dir)

    assert len(imported) == 1
    trace_path = out_dir / "traces" / "imported_case_trial_1.json"
    assert trace_path.exists()
    trace = TraceRun.model_validate_json(trace_path.read_text(encoding="utf-8"))
    assert trace.steps[0]["type"] == "model_call"
    assert trace.steps[1]["tool_name"] == "lookup_order"


def test_cli_trace_export_and_import(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "traces").mkdir(parents=True)
    write_trace(run_dir, _trace())
    out = tmp_path / "openai-trace.json"
    imported = tmp_path / "imported"
    runner = CliRunner()

    export_result = runner.invoke(
        app,
        ["trace", "export", str(run_dir), "--format", "openai-trace", "--out", str(out)],
    )
    import_result = runner.invoke(
        app,
        ["trace", "import", str(out), "--format", "openai-trace", "--out", str(imported)],
    )

    assert export_result.exit_code == 0
    assert import_result.exit_code == 0
    assert (imported / "traces" / "refund_valid_order_trial_1.json").exists()


def test_cli_trace_export_prints_clean_error_for_invalid_trace_artifact(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "traces").mkdir(parents=True)
    (run_dir / "traces" / "bad-trace.json").write_text("{not json", encoding="utf-8")
    out = tmp_path / "openai-trace.json"

    result = CliRunner().invoke(
        app,
        ["trace", "export", str(run_dir), "--format", "openai-trace", "--out", str(out)],
    )

    assert result.exit_code == 1
    assert "Invalid trace artifact:" in result.stderr
    assert "could not parse trace artifact" in result.stderr
    assert "Traceback" not in result.stderr
