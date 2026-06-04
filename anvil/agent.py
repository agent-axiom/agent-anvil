from __future__ import annotations

import importlib
import json
import os
import shlex
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from anvil.scenario import AgentConfig, ExternalAgentConfig
from anvil.trace import TraceRun

AgentRunner = Callable[..., TraceRun]
EVENT_REQUIRED_FIELDS = {
    "model_call": {"model", "output_text", "tool_calls"},
    "tool_call": {"tool_name", "arguments", "result"},
}


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
    payload = _external_agent_payload(
        scenario_id=scenario_id,
        input_text=input_text,
        trial=trial,
        run_id=run_id,
        max_steps=max_steps,
    )
    if config.protocol == "http":
        return _run_http_agent(
            config,
            payload=payload,
            input_text=input_text,
            scenario_id=scenario_id,
            trial=trial,
            run_id=run_id,
            max_steps=max_steps,
            started_at=started_at,
        )

    if config.command is None:
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="invalid_agent_config",
            message="Agent command is required for protocol jsonl.",
        )
    try:
        completed = subprocess.run(
            shlex.split(config.command),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=config.timeout_seconds,
            check=False,
            cwd=config.cwd,
            env={**os.environ, **config.env},
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


def _external_agent_payload(
    *,
    scenario_id: str,
    input_text: str,
    trial: int,
    run_id: str,
    max_steps: int,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "input": input_text,
        "trial": trial,
        "run_id": run_id,
        "max_steps": max_steps,
    }


def _run_http_agent(
    config: ExternalAgentConfig,
    *,
    payload: dict[str, Any],
    input_text: str,
    scenario_id: str,
    trial: int,
    run_id: str,
    max_steps: int,
    started_at: datetime,
) -> TraceRun:
    if config.url is None:
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="invalid_agent_config",
            message="Agent URL is required for protocol http.",
        )

    request = Request(
        config.url,
        data=json.dumps(payload).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **_expanded_headers(config.headers),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            response_body = response.read().decode()
    except TimeoutError:
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="timeout",
            message=f"HTTP agent request timed out after {config.timeout_seconds} seconds.",
        )
    except HTTPError as error:
        body = _read_http_error_body(error)
        message = f"HTTP agent endpoint returned status {error.code}: {body}"
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="http_status",
            message=message,
        )
    except URLError as error:
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="http_error",
            message=f"HTTP agent request failed: {error.reason}",
        )

    try:
        steps, final_output, response_status = _parse_http_trace_response(response_body)
    except ValueError as error:
        message = f"HTTP agent protocol error: {error}"
        return _failed_external_trace(
            run_id=run_id,
            scenario_id=scenario_id,
            trial=trial,
            input_text=input_text,
            started_at=started_at,
            error_type="malformed_http_response",
            message=message,
        )

    status = response_status
    if len(steps) > max_steps:
        status = "failed"

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
    events: list[dict[str, Any]] = []
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
        events.append(event)
    return _parse_trace_events(events)


def _parse_http_trace_response(
    body: str,
) -> tuple[list[dict[str, Any]], str | None, Literal["completed", "failed"]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        msg = f"response body is not valid JSON: {error.msg}"
        raise ValueError(msg) from error
    if not isinstance(payload, dict):
        msg = "response body must be a JSON object"
        raise ValueError(msg)

    response_status = str(payload.get("status", "completed"))
    if response_status not in {"completed", "failed"}:
        msg = "response status must be completed or failed"
        raise ValueError(msg)
    parsed_status = cast("Literal['completed', 'failed']", response_status)

    if "events" in payload:
        events = payload["events"]
        if not isinstance(events, list):
            msg = "response events must be a list"
            raise ValueError(msg)
        steps, final_output = _parse_trace_events(events)
        return steps, final_output, parsed_status

    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        msg = "response steps must be a list"
        raise ValueError(msg)
    events = list(steps)
    if "final_output" in payload:
        events.append({"type": "final_output", "text": payload.get("final_output")})
    parsed_steps, final_output = _parse_trace_events(events)
    return parsed_steps, final_output, parsed_status


def _parse_trace_events(events: list[Any]) -> tuple[list[dict[str, Any]], str | None]:
    steps: list[dict[str, Any]] = []
    final_output: str | None = None
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            msg = f"event {index} must be an object"
            raise ValueError(msg)
        _validate_jsonl_event(event, index)
        if event.get("type") == "final_output":
            final_output = str(event.get("text") or event.get("final_output") or "")
        else:
            steps.append(event)
    return steps, final_output


def _validate_jsonl_event(event: dict[str, Any], line_number: int) -> None:
    event_type = event.get("type")
    if not isinstance(event_type, str) or not event_type:
        msg = f"JSONL event on line {line_number} missing required field: type"
        raise ValueError(msg)

    if event_type == "final_output":
        if not event.get("text") and not event.get("final_output"):
            msg = f"final_output event on line {line_number} missing required fields: text"
            raise ValueError(msg)
        return

    required = EVENT_REQUIRED_FIELDS.get(event_type)
    if required is None:
        msg = f"JSONL event on line {line_number} has unknown type: {event_type}"
        raise ValueError(msg)

    missing = sorted(field for field in required if field not in event)
    if missing:
        msg = (
            f"{event_type} event on line {line_number} missing required fields: "
            f"{', '.join(missing)}"
        )
        raise ValueError(msg)


def _expanded_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: os.path.expandvars(value) for key, value in headers.items()}


def _read_http_error_body(error: HTTPError) -> str:
    body = error.read().decode(errors="replace").strip()
    return body or error.reason
