from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from anvil.storage import write_trace
from anvil.trace import TraceRun


def ingest_jsonl_trace(
    source_file: Path,
    *,
    out_dir: Path,
    scenario_id: str,
    user_input: str,
    trial: int = 1,
    run_id: str | None = None,
) -> Path:
    steps: list[dict[str, Any]] = []
    final_output: str | None = None

    for line_number, raw_line in enumerate(source_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Malformed JSONL on line {line_number}: {error.msg}") from error
        if not isinstance(event, dict):
            raise ValueError(f"Malformed JSONL on line {line_number}: event must be an object")

        event_type = event.get("type")
        if event_type == "final_output":
            final_output = str(event.get("text") or event.get("output_text") or "")
        elif event_type in {"model_call", "tool_call"}:
            steps.append(event)
        else:
            raise ValueError(f"Unsupported JSONL event type on line {line_number}: {event_type}")

    if not final_output:
        raise ValueError("JSONL trace must include a final_output event")

    now = datetime.now(UTC)
    trace = TraceRun(
        run_id=run_id or f"ingest_{now.strftime('%Y%m%d_%H%M%S')}",
        scenario_id=scenario_id,
        trial=trial,
        input=user_input,
        started_at=now,
        ended_at=now,
        status="completed",
        steps=steps,
        final_output=final_output,
    )
    try:
        TraceRun.model_validate(trace)
    except ValidationError as error:
        raise ValueError(f"Imported trace is invalid: {error}") from error

    (out_dir / "traces").mkdir(parents=True, exist_ok=True)
    return write_trace(out_dir, trace)
