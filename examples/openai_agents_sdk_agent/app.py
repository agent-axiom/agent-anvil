from __future__ import annotations

from importlib import import_module
from typing import Any

from examples.openai_agents_sdk_agent.agent import handle_anvil

fastapi: Any = import_module("fastapi")
app = fastapi.FastAPI(title="Agent Anvil OpenAI Agents SDK HTTP Agent")


@app.post("/anvil")
def anvil_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    return handle_anvil(payload)


if __name__ == "__main__":
    uvicorn: Any = import_module("uvicorn")
    uvicorn.run("examples.openai_agents_sdk_agent.app:app", host="127.0.0.1", port=8082)
