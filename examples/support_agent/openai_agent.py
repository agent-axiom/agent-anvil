from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from anvil.config import AnvilSettings
from anvil.trace import TraceRun
from examples.support_agent.tools import (
    TOOL_SCHEMAS,
    escalate_to_human,
    issue_refund,
    lookup_customer,
    lookup_order,
)

TOOL_FUNCTIONS = {
    "lookup_customer": lookup_customer,
    "lookup_order": lookup_order,
    "issue_refund": issue_refund,
    "escalate_to_human": escalate_to_human,
}


def run_agent(
    *,
    input_text: str,
    scenario_id: str,
    trial: int,
    run_id: str,
    max_steps: int,
    client: Any | None = None,
    model: str | None = None,
) -> TraceRun:
    started_at = datetime.now(UTC)
    steps: list[dict[str, Any]] = []
    selected_model = model or AnvilSettings.from_env().openai_model
    selected_client: Any = client or _openai_client()
    input_messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": input_text},
    ]
    final_output: str | None = None
    status = "completed"

    for _ in range(max_steps):
        response = selected_client.responses.create(
            model=selected_model,
            input=input_messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        tool_calls = list(_iter_function_calls(response))
        output_text = _response_output_text(response)
        steps.append(
            {
                "type": "model_call",
                "model": selected_model,
                "input": _last_input(input_messages),
                "output_text": output_text,
                "tool_calls": [
                    {"name": tool_name, "arguments": arguments}
                    for tool_name, arguments, _call_id in tool_calls
                ],
            }
        )

        if not tool_calls:
            final_output = output_text or None
            break

        for tool_name, arguments, call_id in tool_calls:
            result = _call_tool(tool_name, arguments)
            steps.append(
                {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result,
                }
            )
            input_messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                }
            )
    else:
        status = "failed"
        final_output = "Agent reached max_steps before producing a final response."

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


def _openai_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        msg = "OPENAI_API_KEY is required for ANVIL_AGENT_MODE=openai."
        raise RuntimeError(msg)
    return OpenAI()


def _system_prompt() -> str:
    return (Path(__file__).with_name("system_prompt.md")).read_text(encoding="utf-8")


def _iter_function_calls(response: Any) -> Iterable[tuple[str, dict[str, Any], str]]:
    for item in _get(response, "output", []) or []:
        if _get(item, "type") != "function_call":
            continue
        arguments = _get(item, "arguments", "{}") or "{}"
        yield (
            str(_get(item, "name")),
            json.loads(arguments) if isinstance(arguments, str) else dict(arguments),
            str(_get(item, "call_id")),
        )


def _response_output_text(response: Any) -> str:
    direct = _get(response, "output_text", "")
    if isinstance(direct, str) and direct:
        return direct

    chunks: list[str] = []
    for item in _get(response, "output", []) or []:
        if _get(item, "type") != "message":
            continue
        for content in _get(item, "content", []) or []:
            text = _get(content, "text", "")
            if text:
                chunks.append(str(text))
    return "\n".join(chunks)


def _call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = TOOL_FUNCTIONS.get(tool_name)
    if tool is None:
        return {"status": "error", "error": f"unknown tool: {tool_name}"}
    return tool(**arguments)


def _last_input(input_messages: list[dict[str, Any]]) -> str:
    if not input_messages:
        return ""
    return json.dumps(input_messages[-1], ensure_ascii=False)


def _get(value: Any, key: str, default: Any | None = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
