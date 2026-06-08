from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    assertions: list[AssertionCheck] = Field(default_factory=list)


AssertionType = Literal[
    "tool_called",
    "tool_not_called",
    "tool_called_before",
    "min_tool_calls",
    "max_tool_calls",
    "forbidden_arg_value",
    "tool_result_matches",
    "final_output_contains",
    "final_output_not_contains",
]


class AssertionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AssertionType
    tool: str | None = None
    before: str | None = None
    after: str | None = None
    count: int | None = Field(default=None, ge=0)
    path: str | None = None
    values: list[Any] = Field(default_factory=list)
    equals: Any = None
    text: str | None = None

    @model_validator(mode="after")
    def validate_required_fields(self) -> AssertionCheck:
        required_by_type = {
            "tool_called": ("tool",),
            "tool_not_called": ("tool",),
            "tool_called_before": ("before", "after"),
            "min_tool_calls": ("tool", "count"),
            "max_tool_calls": ("tool", "count"),
            "forbidden_arg_value": ("tool", "path"),
            "tool_result_matches": ("tool", "path"),
            "final_output_contains": ("text",),
            "final_output_not_contains": ("text",),
        }
        missing = [
            field for field in required_by_type[self.type] if getattr(self, field) in (None, "")
        ]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{self.type} assertion missing required fields: {joined}")
        return self


class LearnedFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_path: str = Field(min_length=1)
    failure_type: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class ToolPrecondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1)
    result: dict[str, Any] = Field(default_factory=dict)


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destructive_tools: list[str] = Field(default_factory=list)
    require_before: dict[str, list[ToolPrecondition]] = Field(default_factory=dict)
    require_human_approval: list[str] = Field(default_factory=list)


class ScenarioCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    trial_count: int | None = Field(default=None, alias="trials", ge=1)
    max_step_count: int | None = Field(default=None, alias="max_steps", ge=1)
    learned_from: LearnedFrom | None = None

    def trials(self, defaults: ScenarioDefaults) -> int:
        return self.trial_count or defaults.trials

    def max_steps(self, defaults: ScenarioDefaults) -> int:
        return self.max_step_count or defaults.max_steps


class ExternalAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str | None = Field(default=None, min_length=1)
    protocol: Literal["jsonl", "http"] = "jsonl"
    url: str | None = Field(default=None, min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_protocol_config(self) -> ExternalAgentConfig:
        if self.protocol == "jsonl" and not self.command:
            raise ValueError("agent.command is required when protocol is jsonl")
        if self.protocol == "http" and not self.url:
            raise ValueError("agent.url is required when protocol is http")
        return self


AgentConfig = str | ExternalAgentConfig


class ScenarioSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    agent: AgentConfig
    defaults: ScenarioDefaults = Field(default_factory=ScenarioDefaults)
    policies: PolicyConfig = Field(default_factory=PolicyConfig)
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
