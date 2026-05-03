from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScenarioDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trials: int = Field(default=1, ge=1)
    max_steps: int = Field(default=8, ge=1)


class ExpectedBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    should_call_tools: list[str] = Field(default_factory=list)
    should_not_call_tools: list[str] = Field(default_factory=list)
    required_tool_args: dict[str, dict[str, Any]] = Field(default_factory=dict)
    should_ask_clarifying_question: bool = False
    success_criteria: list[str] = Field(default_factory=list)


class ScenarioCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    trial_count: int | None = Field(default=None, alias="trials", ge=1)
    max_step_count: int | None = Field(default=None, alias="max_steps", ge=1)

    def trials(self, defaults: ScenarioDefaults) -> int:
        return self.trial_count or defaults.trials

    def max_steps(self, defaults: ScenarioDefaults) -> int:
        return self.max_step_count or defaults.max_steps


class ExternalAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1)
    protocol: Literal["jsonl"] = "jsonl"
    timeout_seconds: int = Field(default=60, ge=1)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


AgentConfig = str | ExternalAgentConfig


class ScenarioSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    agent: AgentConfig
    defaults: ScenarioDefaults = Field(default_factory=ScenarioDefaults)
    scenarios: list[ScenarioCase] = Field(min_length=1)

    @field_validator("agent")
    @classmethod
    def require_nonempty_agent(cls, agent: AgentConfig) -> AgentConfig:
        if isinstance(agent, str) and not agent.strip():
            raise ValueError("agent must not be empty")
        return agent

    @field_validator("scenarios")
    @classmethod
    def require_unique_scenario_ids(cls, scenarios: list[ScenarioCase]) -> list[ScenarioCase]:
        ids = [scenario.id for scenario in scenarios]
        duplicates = {scenario_id for scenario_id in ids if ids.count(scenario_id) > 1}
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate scenario ids: {joined}")
        return scenarios


def load_scenario_file(path: str | Path) -> ScenarioSuite:
    scenario_path = Path(path)
    payload = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    return ScenarioSuite.model_validate(payload)
