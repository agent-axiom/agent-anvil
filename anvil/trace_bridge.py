from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anvil.storage import write_trace
from anvil.trace import TraceRun

OPENAI_TRACE_FORMAT = "openai-trace"


def export_openai_trace(run_dir: str | Path, *, out_path: str | Path) -> Path:
    selected_run_dir = Path(run_dir)
    traces = [
        _export_trace(TraceRun.model_validate_json(path.read_text(encoding="utf-8")))
        for path in sorted((selected_run_dir / "traces").glob("*.json"))
    ]
    payload = {
        "format": OPENAI_TRACE_FORMAT,
        "run_id": selected_run_dir.name,
        "traces": traces,
    }
    selected_out = Path(out_path)
    selected_out.parent.mkdir(parents=True, exist_ok=True)
    selected_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return selected_out


def import_openai_trace(source_path: str | Path, *, out_dir: str | Path) -> list[TraceRun]:
    payload = json.loads(Path(source_path).read_text(encoding="utf-8"))
    if payload.get("format") != OPENAI_TRACE_FORMAT:
        raise ValueError("trace payload format must be openai-trace")

    selected_out_dir = Path(out_dir)
    (selected_out_dir / "traces").mkdir(parents=True, exist_ok=True)
    selected_run_id = str(payload.get("run_id", selected_out_dir.name))
    traces = [_import_trace(item, run_id=selected_run_id) for item in payload["traces"]]
    for trace in traces:
        write_trace(selected_out_dir, trace)
    return traces


def _export_trace(trace: TraceRun) -> dict[str, Any]:
    return {
        "scenario_id": trace.scenario_id,
        "trial": trace.trial,
        "input": trace.input,
        "status": trace.status,
        "started_at": trace.started_at.isoformat(),
        "ended_at": trace.ended_at.isoformat() if trace.ended_at else None,
        "final_output": trace.final_output,
        "events": [_export_event(step) for step in trace.steps],
    }


def _export_event(step: dict[str, Any]) -> dict[str, Any]:
    if step.get("type") == "model_call":
        return {
            "type": "generation",
            "model": step.get("model"),
            "input": step.get("input"),
            "output_text": step.get("output_text"),
            "tool_calls": step.get("tool_calls", []),
        }
    if step.get("type") == "tool_call":
        return {
            "type": "tool_call",
            "name": step.get("tool_name"),
            "arguments": step.get("arguments", {}),
            "result": step.get("result", {}),
        }
    return dict(step)


def _import_trace(item: dict[str, Any], *, run_id: str) -> TraceRun:
    now = datetime.now(UTC)
    return TraceRun(
        run_id=run_id,
        scenario_id=str(item.get("scenario_id", "imported_trace")),
        trial=int(item.get("trial", 1)),
        input=str(item.get("input", "")),
        started_at=_parse_datetime(item.get("started_at")) or now,
        ended_at=_parse_datetime(item.get("ended_at")) or now,
        status=str(item.get("status", "completed")),
        steps=[_import_event(event) for event in item.get("events", [])],
        final_output=item.get("final_output"),
    )


def _import_event(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("type") == "generation":
        return {
            "type": "model_call",
            "model": event.get("model"),
            "input": event.get("input", ""),
            "output_text": event.get("output_text", ""),
            "tool_calls": event.get("tool_calls", []),
        }
    if event.get("type") == "tool_call":
        return {
            "type": "tool_call",
            "tool_name": event.get("name"),
            "arguments": event.get("arguments", {}),
            "result": event.get("result", {}),
        }
    return dict(event)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value)
