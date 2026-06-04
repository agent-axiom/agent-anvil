from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, TextIO


def read_payload(*, stdin: TextIO | None = None) -> dict[str, Any]:
    source = stdin or sys.stdin
    payload = json.loads(source.read())
    if not isinstance(payload, dict):
        msg = "Agent Anvil stdin payload must be a JSON object."
        raise TypeError(msg)
    return payload


def emit_model_call(
    *,
    model: str,
    input_text: Any = None,
    output_text: str,
    tool_calls: Sequence[Mapping[str, Any]] | None = None,
    stdout: TextIO | None = None,
) -> None:
    emit_event(
        {
            "type": "model_call",
            "model": model,
            "input": input_text,
            "output_text": output_text,
            "tool_calls": list(tool_calls or []),
        },
        stdout=stdout,
    )


def emit_tool_call(
    *,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
    result: Any = None,
    stdout: TextIO | None = None,
) -> None:
    emit_event(
        {
            "type": "tool_call",
            "tool_name": tool_name,
            "arguments": dict(arguments or {}),
            "result": result,
        },
        stdout=stdout,
    )


def emit_final_output(text: str, *, stdout: TextIO | None = None) -> None:
    emit_event({"type": "final_output", "text": text}, stdout=stdout)


def emit_event(event: Mapping[str, Any], *, stdout: TextIO | None = None) -> None:
    sink = stdout or sys.stdout
    sink.write(json.dumps(dict(event), separators=(",", ":")))
    sink.write("\n")
    sink.flush()
