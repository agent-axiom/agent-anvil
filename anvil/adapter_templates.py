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

    """Agent Anvil external JSONL adapter for OpenAI Agents SDK.

    Requires:
        pip install openai-agents agent-anvil

    Verify:
        uv run anvil conformance external-agent --agent-command "python openai_agents_adapter.py"

    The OpenAI Agents SDK Runner manages the tool loop. If you need exact tool-call
    trace events, wrap your local tools and call `emit_tool_call(...)` after each
    tool execution.
    """

    from agents import Agent, Runner

    from anvil.external import emit_final_output, emit_model_call, read_payload


    def build_agent() -> Agent:
        return Agent(
            name="EvaluatedAgent",
            instructions=(
                "You are being evaluated by Agent Anvil. Complete the user task "
                "and respect tool safety preconditions."
            ),
        )


    def run_agent(input_text: str, max_steps: int) -> str:
        agent = build_agent()
        result = Runner.run_sync(agent, input_text, max_turns=max_steps)
        return str(result.final_output or "")


    def main() -> None:
        payload = read_payload()
        input_text = str(payload["input"])
        max_steps = int(payload.get("max_steps", 8))

        final_output = run_agent(input_text, max_steps)
        emit_model_call(
            model="openai-agents-sdk",
            input_text=input_text,
            output_text=final_output,
            tool_calls=[],
        )
        emit_final_output(final_output)


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
        description="External JSONL adapter starter for the OpenAI Agents SDK Runner.",
        dependency_hint="pip install openai-agents agent-anvil",
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
