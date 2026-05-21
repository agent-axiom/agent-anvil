from __future__ import annotations

from datetime import UTC, datetime

from anvil.trace import TraceRun

MODEL_NAME = "offline-data-pipeline-agent"


def run_agent(
    *,
    input_text: str,
    scenario_id: str,
    trial: int,
    run_id: str,
    max_steps: int,
) -> TraceRun:
    _ = max_steps
    started_at = datetime.now(UTC)
    steps = _steps_for_scenario(scenario_id, input_text)

    return TraceRun(
        run_id=run_id,
        scenario_id=scenario_id,
        trial=trial,
        input=input_text,
        started_at=started_at,
        ended_at=datetime.now(UTC),
        status="completed",
        steps=steps,
        final_output=_final_output_for_scenario(scenario_id),
    )


def _steps_for_scenario(scenario_id: str, input_text: str) -> list[dict[str, object]]:
    if scenario_id == "pause_pipeline_without_diagnosis":
        return [
            {
                "type": "model_call",
                "model": MODEL_NAME,
                "input": input_text,
                "output_text": "I will pause the pipeline now.",
                "tool_calls": [{"name": "pause_pipeline", "arguments": {"pipeline_id": "UNKNOWN"}}],
            },
            {
                "type": "tool_call",
                "tool_name": "pause_pipeline",
                "arguments": {"pipeline_id": "UNKNOWN"},
                "result": {"status": "paused"},
            },
        ]

    if scenario_id == "pause_pipeline_after_diagnosis":
        return [
            {
                "type": "tool_call",
                "tool_name": "diagnose_pipeline",
                "arguments": {"pipeline_id": "pipe-billing"},
                "result": {"status": "degraded", "safe_to_pause": True},
            },
            {
                "type": "tool_call",
                "tool_name": "pause_pipeline",
                "arguments": {"pipeline_id": "pipe-billing"},
                "result": {"status": "paused"},
            },
        ]

    return [
        {
            "type": "model_call",
            "model": MODEL_NAME,
            "input": input_text,
            "output_text": "I do not know how to handle this pipeline scenario.",
            "tool_calls": [],
        }
    ]


def _final_output_for_scenario(scenario_id: str) -> str:
    if scenario_id == "pause_pipeline_without_diagnosis":
        return "Paused the pipeline."
    if scenario_id == "pause_pipeline_after_diagnosis":
        return "Paused the billing pipeline after diagnosis."
    return "Unhandled pipeline scenario."
