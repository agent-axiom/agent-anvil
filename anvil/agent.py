from __future__ import annotations

import importlib
import json
import shlex
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from anvil.scenario import AgentConfig, ExternalAgentConfig
from anvil.trace import TraceRun

AgentRunner = Callable[..., TraceRun]


def load_agent_runner(agent_config: AgentConfig) -> AgentRunner:
    if isinstance(agent_config, ExternalAgentConfig):
        return lambda **kwargs: run_external_agent(agent_config, **kwargs)

    module = importlib.import_module(agent_config)
    return module.run_agent


def run_external_agent(
    config: ExternalAgentConfig,
    *,
    input_text: str,
    scenario_id: str,
    trial: int,
    run_id: str,
    max_steps: int,
    agent_mode: str | None = None,
) -> TraceRun:
    _ = agent_mode
    started_at = datetime.now(UTC)
    payload = {
        "scenario_id": scenario_id,
        "input": input_text,
        "trial": trial,
        "run_id": run_id,
        "max_steps": max_steps,
    }
    try:
        completed = subprocess.run(
            shlex.split(config.command),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=config.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="timeout",
            message=f"Agent command timed out after {config.timeout_seconds} seconds.",
        )

    try:
        steps, final_output = _parse_jsonl_trace_events(completed.stdout)
    except ValueError as error:
        message = f"Agent protocol error: {error}"
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="malformed_jsonl",
            message=message,
        )

    status = "completed"
    if completed.returncode != 0 or len(steps) > max_steps:
        status = "failed"
    if completed.returncode != 0 and not final_output:
        final_output = (
            completed.stderr.strip() or f"Agent command exited with {completed.returncode}."
        )

    return TraceRun(
        run_id=run_id,
        scenario_id=scenario_id,
        trial=trial,
        input=input_text,
        started_at=started_at,
        ended_at=datetime.now(UTC),
        status=status,
        steps=steps,
        final_output=final_output,
    )


def _failed_external_trace(
    *,
    run_id: str,
    scenario_id: str,
    trial: int,
    input_text: str,
    started_at: datetime,
    error_type: str,
    message: str,
) -> TraceRun:
    return TraceRun(
        run_id=run_id,
        scenario_id=scenario_id,
        trial=trial,
        input=input_text,
        started_at=started_at,
        ended_at=datetime.now(UTC),
        status="failed",
        steps=[
            {
                "type": "agent_protocol_error",
                "error_type": error_type,
                "message": message,
            }
        ],
        final_output=message,
    )


def _parse_jsonl_trace_events(stdout: str) -> tuple[list[dict[str, Any]], str | None]:
    steps: list[dict[str, Any]] = []
    final_output: str | None = None
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            msg = f"JSONL event on line {line_number} is not valid JSON: {error.msg}"
            raise ValueError(msg) from error
        if not isinstance(event, dict):
            msg = f"JSONL event on line {line_number} must be an object"
            raise ValueError(msg)
        if event.get("type") == "final_output":
            final_output = str(event.get("text") or event.get("final_output") or "")
        else:
            steps.append(event)
    return steps, final_output
