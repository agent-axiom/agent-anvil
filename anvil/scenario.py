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

    @model_validator(mode="after")
    def validate_tool_contracts(self) -> ExpectedBehavior:
        _validate_tool_name_list("expected", self.should_call_tools)
        _validate_tool_name_list("forbidden", self.should_not_call_tools)
        _validate_required_tool_arg_names(self.required_tool_args)

        required = set(self.should_call_tools)
        forbidden = set(self.should_not_call_tools)
        overlap = sorted(required & forbidden)
        if overlap:
            joined = ", ".join(overlap)
            raise ValueError(f"tools cannot be both required and forbidden: {joined}")

        args_forbidden = sorted(set(self.required_tool_args) & forbidden)
        if args_forbidden:
            joined = ", ".join(args_forbidden)
            raise ValueError(f"required args cannot target forbidden tools: {joined}")
        _validate_assertion_contracts(self)
        return self


def _validate_assertion_contracts(expected: ExpectedBehavior) -> None:
    required = set(expected.should_call_tools)
    forbidden = set(expected.should_not_call_tools)
    min_counts = dict.fromkeys(required, 1)
    max_counts = dict.fromkeys(forbidden, 0)

    for assertion in expected.assertions:
        if assertion.type == "tool_called" and assertion.tool is not None:
            required.add(assertion.tool)
            min_counts[assertion.tool] = max(min_counts.get(assertion.tool, 0), 1)
        if assertion.type == "tool_not_called" and assertion.tool is not None:
            forbidden.add(assertion.tool)
            max_counts[assertion.tool] = min(max_counts.get(assertion.tool, 0), 0)
        if assertion.type == "tool_sequence":
            _validate_nonempty_tool_names(assertion.tools)
            forbidden_in_sequence = sorted(set(assertion.tools) & forbidden)
            if forbidden_in_sequence:
                joined = ", ".join(forbidden_in_sequence)
                raise ValueError(f"tool_sequence cannot include forbidden tools: {joined}")
        if assertion.type == "min_tool_calls" and assertion.tool is not None:
            min_counts[assertion.tool] = max(
                min_counts.get(assertion.tool, 0),
                assertion.count or 0,
            )
        if assertion.type == "max_tool_calls" and assertion.tool is not None:
            max_counts[assertion.tool] = min(
                max_counts.get(assertion.tool, assertion.count or 0),
                assertion.count or 0,
            )

    overlap = sorted(required & forbidden)
    if overlap:
        joined = ", ".join(overlap)
        raise ValueError(f"tools cannot be both required and forbidden by assertions: {joined}")

    for tool_name, minimum in min_counts.items():
        maximum = max_counts.get(tool_name)
        if maximum is not None and minimum > maximum:
            raise ValueError(
                f"min_tool_calls cannot exceed max_tool_calls for {tool_name}: "
                f"{minimum} > {maximum}"
            )


def _validate_nonempty_tool_names(tool_names: list[str]) -> None:
    invalid = [tool_name for tool_name in tool_names if not tool_name.strip()]
    if invalid:
        raise ValueError("tool names must not be empty")


def _validate_tool_name_list(kind: str, tool_names: list[str]) -> None:
    _validate_nonempty_tool_names(tool_names)

    duplicates = sorted({tool_name for tool_name in tool_names if tool_names.count(tool_name) > 1})
    if duplicates:
        label = "expected" if kind == "expected" else "forbidden"
        joined = ", ".join(duplicates)
        raise ValueError(f"duplicate {label} tool names: {joined}")


def _validate_required_tool_arg_names(required_tool_args: dict[str, dict[str, Any]]) -> None:
    invalid = [tool_name for tool_name in required_tool_args if not tool_name.strip()]
    if invalid:
        raise ValueError("tool names must not be empty")


AssertionType = Literal[
    "tool_called",
    "tool_not_called",
    "tool_called_before",
    "tool_sequence",
    "min_tool_calls",
    "max_tool_calls",
    "tool_argument_matches",
    "forbidden_arg_value",
    "tool_result_matches",
    "final_output_contains",
    "final_output_not_contains",
    "metric_lte",
    "metric_gte",
    "no_tool_errors",
    "tool_retried_after_error",
]

MetricName = Literal[
    "latency_ms",
    "tool_call_count",
    "model_call_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
]


class AssertionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AssertionType
    tool: str | None = None
    tools: list[str] = Field(default_factory=list)
    before: str | None = None
    after: str | None = None
    count: int | None = Field(default=None, ge=0)
    path: str | None = None
    values: list[Any] = Field(default_factory=list)
    equals: Any = None
    text: str | None = None
    metric: MetricName | None = None
    value: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_required_fields(self) -> AssertionCheck:
        required_by_type = {
            "tool_called": ("tool",),
            "tool_not_called": ("tool",),
            "tool_called_before": ("before", "after"),
            "tool_sequence": ("tools",),
            "min_tool_calls": ("tool", "count"),
            "max_tool_calls": ("tool", "count"),
            "tool_argument_matches": ("tool", "path", "equals"),
            "forbidden_arg_value": ("tool", "path"),
            "tool_result_matches": ("tool", "path", "equals"),
            "final_output_contains": ("text",),
            "final_output_not_contains": ("text",),
            "metric_lte": ("metric", "value"),
            "metric_gte": ("metric", "value"),
            "no_tool_errors": (),
            "tool_retried_after_error": ("tool",),
        }
        missing = [
            field
            for field in required_by_type[self.type]
            if _required_assertion_field_missing(self, field)
        ]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{self.type} assertion missing required fields: {joined}")
        return self


def _required_assertion_field_missing(assertion: AssertionCheck, field: str) -> bool:
    if field == "equals":
        return field not in assertion.model_fields_set
    if field == "value":
        return field not in assertion.model_fields_set or assertion.value is None
    return getattr(assertion, field) in (None, "", [])


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
