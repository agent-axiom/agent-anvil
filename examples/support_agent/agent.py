from __future__ import annotations

import os

from anvil.trace import TraceRun
from examples.support_agent.deterministic_agent import run_agent as run_offline_agent
from examples.support_agent.openai_agent import run_agent as run_openai_agent


def run_agent(
    *,
    input_text: str,
    scenario_id: str,
    trial: int,
    run_id: str,
    max_steps: int,
    agent_mode: str | None = None,
) -> TraceRun:
    selected_mode = (agent_mode or os.getenv("ANVIL_AGENT_MODE") or "offline").lower()
    if selected_mode == "auto":
        selected_mode = "openai" if os.getenv("OPENAI_API_KEY") else "offline"

    if selected_mode == "offline":
        return run_offline_agent(
            input_text=input_text,
            scenario_id=scenario_id,
            trial=trial,
            run_id=run_id,
            max_steps=max_steps,
        )
    if selected_mode == "openai":
        return run_openai_agent(
            input_text=input_text,
            scenario_id=scenario_id,
            trial=trial,
            run_id=run_id,
            max_steps=max_steps,
        )

    msg = f"unsupported support agent mode: {selected_mode}"
    raise ValueError(msg)
