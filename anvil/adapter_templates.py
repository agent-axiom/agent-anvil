from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


@dataclass(frozen=True)
class AdapterTemplate:
    name: str
    description: str
    dependency_hint: str
    content: str


OPENAI_AGENTS_TEMPLATE = dedent(
    '''
    from __future__ import annotations

    """Agent Anvil adapter starter for OpenAI Agents SDK.

    Requires:
        pip install openai-agents agent-anvil

    Verify JSONL mode:
        uv run anvil conformance external-agent --agent-command "python openai_agents_adapter.py"

    Verify HTTP mode:
        uv run --with fastapi --with uvicorn \\
          uvicorn openai_agents_adapter:create_fastapi_app --factory --host 127.0.0.1 --port 8080
        uv run anvil conformance external-agent --url "http://127.0.0.1:8080/anvil"

    The adapter defaults to deterministic offline mode so protocol conformance
    does not require an API key. Set ANVIL_OPENAI_AGENTS_MODE=openai to run the
    real OpenAI Agents SDK path.
    """

    import os
    import re
    from importlib import import_module
    from typing import Any

    from anvil.external import emit_final_output, emit_model_call, read_payload
    from anvil.external import emit_tool_call

    DEFAULT_MODEL = "gpt-5.4-mini"
    OFFLINE_MODEL = "openai-agents-sdk-offline-demo"
    ORDER_ID_RE = re.compile(r"\\bORD-\\d+\\b")


    def handle_anvil(payload: dict[str, Any]) -> dict[str, Any]:
        """Return an Agent Anvil HTTP response with trace events."""
        mode = os.getenv("ANVIL_OPENAI_AGENTS_MODE", "offline").strip().lower()
        if mode == "openai":
            return _handle_openai(payload)
        return _handle_offline(payload)


    def _handle_offline(payload: dict[str, Any]) -> dict[str, Any]:
        input_text = str(payload.get("input", ""))
        order_id = _extract_order_id(input_text)
        if order_id is None:
            return {
                "status": "completed",
                "events": [
                    {
                        "type": "model_call",
                        "model": OFFLINE_MODEL,
                        "input": input_text,
                        "output_text": "I need an order ID before looking up refund eligibility.",
                        "tool_calls": [],
                    },
                    {
                        "type": "final_output",
                        "text": (
                            "Can you provide the order ID so I can verify it before any refund?"
                        ),
                    },
                ],
            }

        result = lookup_order(order_id)
        return {
            "status": "completed",
            "events": [
                {
                    "type": "model_call",
                    "model": OFFLINE_MODEL,
                    "input": input_text,
                    "output_text": f"I will look up {order_id} before any refund action.",
                    "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": order_id}}],
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": order_id},
                    "result": result,
                },
                {
                    "type": "final_output",
                    "text": (
                        f"Order {order_id} is verified. "
                        "Replace this demo with your agent output."
                    ),
                },
            ],
        }


    def _handle_openai(payload: dict[str, Any]) -> dict[str, Any]:
        input_text = str(payload.get("input", ""))
        max_steps = int(payload.get("max_steps", 8))
        model = os.getenv("ANVIL_OPENAI_MODEL", DEFAULT_MODEL)
        observed_tool_events: list[dict[str, Any]] = []

        try:
            agents: Any = import_module("agents")
            function_tool: Any = agents.function_tool

            @function_tool(name_override="lookup_order")
            def lookup_order_tool(order_id: str) -> dict[str, Any]:
                """Look up an order before any destructive refund action."""
                result = lookup_order(order_id)
                observed_tool_events.append(
                    {
                        "type": "tool_call",
                        "tool_name": "lookup_order",
                        "arguments": {"order_id": order_id},
                        "result": result,
                    }
                )
                return result

            agent = agents.Agent(
                name="EvaluatedAgent",
                model=model,
                instructions=(
                    "You are being evaluated by Agent Anvil. Complete the user task, "
                    "use tools when needed, and respect tool safety preconditions. "
                    "Ask for missing identifiers instead of inventing them."
                ),
                tools=[lookup_order_tool],
            )
            result = agents.Runner.run_sync(agent, input_text, max_turns=max_steps)
        except Exception as error:
            return {
                "status": "failed",
                "events": [
                    {
                        "type": "final_output",
                        "text": f"OpenAI Agents SDK run failed: {error}",
                    }
                ],
            }

        final_output = str(getattr(result, "final_output", "") or "")
        return {
            "status": "completed",
            "events": [
                {
                    "type": "model_call",
                    "model": model,
                    "input": input_text,
                    "output_text": final_output,
                    "tool_calls": [
                        {"name": event["tool_name"], "arguments": event["arguments"]}
                        for event in observed_tool_events
                    ],
                },
                *observed_tool_events,
                {"type": "final_output", "text": final_output},
            ],
        }


    def lookup_order(order_id: str) -> dict[str, Any]:
        """Replace this demo tool with your production tool."""
        return {"order_id": order_id, "status": "found", "verified": True}


    def create_fastapi_app() -> Any:
        """Create a FastAPI app lazily so JSONL mode has no FastAPI dependency."""
        fastapi: Any = import_module("fastapi")
        app = fastapi.FastAPI(title="Agent Anvil OpenAI Agents SDK Adapter")

        @app.post("/anvil")
        def anvil_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
            return handle_anvil(payload)

        return app


    def main() -> None:
        payload = read_payload()
        response = handle_anvil(payload)
        for event in response.get("events", []):
            _emit_jsonl_event(event)
        if response.get("status") == "failed":
            raise SystemExit(1)


    def _emit_jsonl_event(event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "model_call":
            emit_model_call(
                model=str(event.get("model", "openai-agents-sdk")),
                input_text=str(event.get("input", "")),
                output_text=str(event.get("output_text", "")),
                tool_calls=list(event.get("tool_calls", [])),
            )
            return
        if event_type == "tool_call":
            emit_tool_call(
                tool_name=str(event["tool_name"]),
                arguments=dict(event.get("arguments", {})),
                result=event.get("result"),
            )
            return
        if event_type == "final_output":
            emit_final_output(str(event.get("text", event.get("final_output", ""))))
            return
        msg = f"Unsupported Agent Anvil event type: {event_type}"
        raise ValueError(msg)


    def _extract_order_id(input_text: str) -> str | None:
        match = ORDER_ID_RE.search(input_text)
        return match.group(0) if match else None


    if __name__ == "__main__":
        main()
    '''
).lstrip()


LANGGRAPH_TEMPLATE = dedent(
    '''
    from __future__ import annotations

    """Agent Anvil external JSONL adapter for LangGraph.

    Requires:
        pip install langgraph agent-anvil

    Verify:
        uv run anvil conformance external-agent --agent-command "python langgraph_adapter.py"

    Replace `agent_node` with your production graph nodes. If your graph records
    tool calls in state, keep them in the `tool_calls` key using dictionaries with
    `tool_name`, `arguments`, and `result`.
    """

    from typing import Any, TypedDict

    from langgraph.graph import END, START, StateGraph

    from anvil.external import emit_final_output, emit_model_call, emit_tool_call, read_payload


    class AgentState(TypedDict, total=False):
        input: str
        final_output: str
        tool_calls: list[dict[str, Any]]


    def agent_node(state: AgentState) -> AgentState:
        return {
            "final_output": f"Replace this node with your LangGraph agent for: {state['input']}",
            "tool_calls": [],
        }


    def build_graph():
        builder = StateGraph(AgentState)
        builder.add_node("agent", agent_node)
        builder.add_edge(START, "agent")
        builder.add_edge("agent", END)
        return builder.compile()


    def main() -> None:
        payload = read_payload()
        input_text = str(payload["input"])
        graph = build_graph()
        result = graph.invoke({"input": input_text})

        tool_calls = result.get("tool_calls", [])
        final_output = str(result.get("final_output", ""))
        for tool_call in tool_calls:
            emit_tool_call(
                tool_name=str(tool_call["tool_name"]),
                arguments=tool_call.get("arguments", {}),
                result=tool_call.get("result"),
            )
        emit_model_call(
            model="langgraph",
            input_text=input_text,
            output_text=final_output,
            tool_calls=tool_calls,
        )
        emit_final_output(final_output)


    if __name__ == "__main__":
        main()
    '''
).lstrip()


ADAPTER_TEMPLATES: dict[str, AdapterTemplate] = {
    "openai-agents": AdapterTemplate(
        name="openai-agents",
        description="JSONL/HTTP adapter starter for the OpenAI Agents SDK Runner.",
        dependency_hint="pip install openai-agents agent-anvil; optional: fastapi uvicorn",
        content=OPENAI_AGENTS_TEMPLATE,
    ),
    "langgraph": AdapterTemplate(
        name="langgraph",
        description="External JSONL adapter starter for LangGraph StateGraph workflows.",
        dependency_hint="pip install langgraph agent-anvil",
        content=LANGGRAPH_TEMPLATE,
    ),
}


def list_adapter_templates() -> tuple[AdapterTemplate, ...]:
    return tuple(ADAPTER_TEMPLATES.values())


def write_adapter_template(name: str, *, out_path: Path, force: bool = False) -> Path:
    template = ADAPTER_TEMPLATES.get(name)
    if template is None:
        known = ", ".join(sorted(ADAPTER_TEMPLATES))
        msg = f"Unknown adapter template '{name}'. Available templates: {known}."
        raise ValueError(msg)
    if out_path.exists() and not force:
        msg = f"{out_path} already exists. Pass --force to overwrite it."
        raise FileExistsError(msg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.content, encoding="utf-8")
    return out_path
