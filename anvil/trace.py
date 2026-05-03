from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TraceStatus = Literal["running", "completed", "failed"]


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
    steps: list[dict[str, Any]] = Field(default_factory=list)
    final_output: str | None = None
    metrics: TraceMetrics = Field(default_factory=TraceMetrics)

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

    def tool_calls(self) -> list[dict[str, Any]]:
        return [step for step in self.steps if step.get("type") == "tool_call"]

    def tool_names(self) -> list[str]:
        return [str(step.get("tool_name")) for step in self.tool_calls()]
