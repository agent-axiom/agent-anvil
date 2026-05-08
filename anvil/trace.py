from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator, model_validator

TraceStatus = Literal["running", "completed", "failed"]


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str

    def get(self, key: str, default: Any = None) -> Any:
        return self.model_dump(mode="python").get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.model_dump(mode="python")[key]

    def __contains__(self, key: object) -> bool:
        return key in self.model_dump(mode="python")

    def items(self) -> Any:
        return self.model_dump(mode="python").items()


class ModelCallStep(TraceStep):
    type: Literal["model_call"] = "model_call"
    model: str | None = None
    input: Any = None
    output_text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class ToolCallStep(TraceStep):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None


class FunctionCallOutputStep(TraceStep):
    type: Literal["function_call_output"] = "function_call_output"
    call_id: str | None = None
    output: str | dict[str, Any] | None = None


class ToolArgumentErrorStep(TraceStep):
    type: Literal["tool_argument_error"] = "tool_argument_error"
    tool_name: str | None = None
    arguments: Any = None
    error: str | None = None
    message: str | None = None


class ToolExecutionErrorStep(TraceStep):
    type: Literal["tool_execution_error"] = "tool_execution_error"
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    message: str | None = None


class AgentProtocolErrorStep(TraceStep):
    type: Literal["agent_protocol_error"] = "agent_protocol_error"
    error_type: str
    message: str


class FinalOutputStep(TraceStep):
    type: Literal["final_output"] = "final_output"
    text: str | None = None
    final_output: str | None = None


TRACE_STEP_TYPES: dict[str, type[TraceStep]] = {
    "model_call": ModelCallStep,
    "tool_call": ToolCallStep,
    "function_call_output": FunctionCallOutputStep,
    "tool_argument_error": ToolArgumentErrorStep,
    "tool_execution_error": ToolExecutionErrorStep,
    "agent_protocol_error": AgentProtocolErrorStep,
    "final_output": FinalOutputStep,
}

TraceStepInput = TraceStep | Mapping[str, Any]


def parse_trace_step(value: TraceStepInput) -> TraceStep:
    if isinstance(value, TraceStep):
        return value
    step_type = value.get("type")
    model = TRACE_STEP_TYPES.get(str(step_type), TraceStep)
    return model.model_validate(dict(value))


class TraceMetrics(BaseModel):
    latency_ms: int = 0
    tool_call_count: int = 0
    model_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class TraceRun(BaseModel):
    run_id: str
    scenario_id: str
    trial: int = Field(ge=1)
    input: str
    started_at: datetime
    ended_at: datetime | None = None
    status: TraceStatus
    steps: Sequence[SerializeAsAny[TraceStep] | Mapping[str, Any]] = Field(default_factory=list)
    final_output: str | None = None
    metrics: TraceMetrics = Field(default_factory=TraceMetrics)

    @field_validator("steps", mode="before")
    @classmethod
    def validate_steps(cls, value: Any) -> list[TraceStep]:
        if value is None:
            return []
        if not isinstance(value, list):
            msg = "steps must be a list"
            raise TypeError(msg)
        return [parse_trace_step(step) for step in value]

    @model_validator(mode="after")
    def refresh_metrics(self) -> TraceRun:
        latency_ms = 0
        if self.ended_at is not None:
            latency_ms = max(int((self.ended_at - self.started_at).total_seconds() * 1000), 0)

        self.metrics = TraceMetrics(
            latency_ms=latency_ms,
            tool_call_count=sum(1 for step in self.steps if step.get("type") == "tool_call"),
            model_call_count=sum(1 for step in self.steps if step.get("type") == "model_call"),
            input_tokens=self.metrics.input_tokens,
            output_tokens=self.metrics.output_tokens,
            total_tokens=self.metrics.total_tokens,
            estimated_cost_usd=self.metrics.estimated_cost_usd,
        )
        return self

    def tool_calls(self) -> list[SerializeAsAny[TraceStep] | Mapping[str, Any]]:
        return [step for step in self.steps if step.get("type") == "tool_call"]

    def tool_names(self) -> list[str]:
        return [str(step.get("tool_name")) for step in self.tool_calls()]
