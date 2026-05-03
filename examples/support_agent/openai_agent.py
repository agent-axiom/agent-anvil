from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from openai import OpenAI

from anvil.config import AnvilSettings
from anvil.trace import TraceMetrics, TraceRun
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
MODEL_TOKEN_PRICES_USD_PER_1M = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5-mini": (0.25, 2.00),
}


class ToolArgumentError(ValueError):
    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name


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
    input_messages: list[Any] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": input_text},
    ]
    final_output: str | None = None
    status = "completed"
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    for _ in range(max_steps):
        response = selected_client.responses.create(
            model=selected_model,
            input=input_messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        usage = _response_usage(response)
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
        total_tokens += usage["total_tokens"]
        output_text = _response_output_text(response)
        try:
            tool_calls = list(_iter_function_calls(response))
        except ToolArgumentError as error:
            steps.append(
                {
                    "type": "model_call",
                    "model": selected_model,
                    "input": _last_input(input_messages),
                    "output_text": output_text,
                    "tool_calls": [],
                }
            )
            steps.append(
                {
                    "type": "tool_argument_error",
                    "tool_name": error.tool_name,
                    "message": str(error),
                }
            )
            status = "failed"
            final_output = str(error)
            break
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

        input_messages.extend(_get(response, "output", []) or [])
        for tool_name, arguments, call_id in tool_calls:
            try:
                result = _call_tool(tool_name, arguments)
            except (TypeError, ValueError, KeyError) as error:
                final_output = f"Tool execution failed for {tool_name}: {error}"
                steps.append(
                    {
                        "type": "tool_execution_error",
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "message": final_output,
                    }
                )
                status = "failed"
                break
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
        if status == "failed":
            break
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
        metrics=TraceMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=_estimate_cost_usd(selected_model, input_tokens, output_tokens),
        ),
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
        tool_name = str(_get(item, "name"))
        try:
            parsed_arguments = (
                json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
            )
        except (JSONDecodeError, TypeError, ValueError) as error:
            msg = f"Invalid JSON tool arguments for {tool_name}: {error}"
            raise ToolArgumentError(tool_name, msg) from error
        yield (
            tool_name,
            parsed_arguments,
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


def _last_input(input_messages: list[Any]) -> str:
    if not input_messages:
        return ""
    last_input = input_messages[-1]
    if isinstance(last_input, dict):
        return json.dumps(last_input, ensure_ascii=False)
    return str(last_input)


def _response_usage(response: Any) -> dict[str, int]:
    usage = _get(response, "usage", {}) or {}
    input_tokens = _int_or_zero(_get(usage, "input_tokens", 0))
    output_tokens = _int_or_zero(_get(usage, "output_tokens", 0))
    total_tokens = _int_or_zero(_get(usage, "total_tokens", input_tokens + output_tokens))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens or input_tokens + output_tokens,
    }


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    for model_prefix, prices in sorted(
        MODEL_TOKEN_PRICES_USD_PER_1M.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if model.startswith(model_prefix):
            input_price, output_price = prices
            return round(
                ((input_tokens * input_price) + (output_tokens * output_price)) / 1_000_000,
                8,
            )
    return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _get(value: Any, key: str, default: Any | None = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
