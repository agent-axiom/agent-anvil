from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from openai import OpenAI
from pydantic import BaseModel, Field

from anvil.config import DEFAULT_OPENAI_MODEL
from anvil.scenario import ScenarioCase, ScenarioDefaults
from anvil.trace import TraceRun


class DeterministicCheck(StrEnum):
    EXPECTED_TOOLS_CALLED = "expected_tools_called"
    FORBIDDEN_TOOL_NOT_CALLED = "forbidden_tool_not_called"
    MAX_STEPS_NOT_EXCEEDED = "max_steps_not_exceeded"
    REQUIRED_TOOL_ARGS_MATCHED = "required_tool_args_matched"
    FINAL_OUTPUT_EXISTS = "final_output_exists"


class CheckOutcome(BaseModel):
    name: DeterministicCheck
    passed: bool
    reason: str


class DeterministicGrade(BaseModel):
    passed: bool
    checks: list[CheckOutcome]


class SemanticGrade(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    failure_type: str = "none"
    severity: str = "none"
    reason: str = ""
    suggested_fix: dict[str, str] = Field(default_factory=dict)


class GradeResult(BaseModel):
    scenario_id: str
    trial: int
    passed: bool
    deterministic_passed: bool
    semantic: SemanticGrade
    trace_path: str
    deterministic_checks: list[CheckOutcome] = Field(default_factory=list)


class SemanticGrader(Protocol):
    def grade(self, scenario: ScenarioCase, trace: TraceRun) -> SemanticGrade: ...


def deterministic_grade_trace(
    scenario: ScenarioCase,
    trace: TraceRun,
    defaults: ScenarioDefaults,
) -> DeterministicGrade:
    checks = [
        _expected_tools_called(scenario, trace),
        _forbidden_tools_not_called(scenario, trace),
        _max_steps_not_exceeded(scenario, trace, defaults),
        _required_tool_args_matched(scenario, trace),
        _final_output_exists(trace),
    ]
    return DeterministicGrade(passed=all(check.passed for check in checks), checks=checks)


def _expected_tools_called(scenario: ScenarioCase, trace: TraceRun) -> CheckOutcome:
    called = set(trace.tool_names())
    missing = [tool for tool in scenario.expected.should_call_tools if tool not in called]
    return CheckOutcome(
        name=DeterministicCheck.EXPECTED_TOOLS_CALLED,
        passed=not missing,
        reason="all expected tools were called"
        if not missing
        else f"missing expected tool calls: {', '.join(missing)}",
    )


def _forbidden_tools_not_called(scenario: ScenarioCase, trace: TraceRun) -> CheckOutcome:
    called = set(trace.tool_names())
    forbidden = [tool for tool in scenario.expected.should_not_call_tools if tool in called]
    return CheckOutcome(
        name=DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED,
        passed=not forbidden,
        reason="no forbidden tools were called"
        if not forbidden
        else f"forbidden tool calls observed: {', '.join(forbidden)}",
    )


def _max_steps_not_exceeded(
    scenario: ScenarioCase,
    trace: TraceRun,
    defaults: ScenarioDefaults,
) -> CheckOutcome:
    max_steps = scenario.max_steps(defaults)
    return CheckOutcome(
        name=DeterministicCheck.MAX_STEPS_NOT_EXCEEDED,
        passed=len(trace.steps) <= max_steps,
        reason=f"{len(trace.steps)} steps observed, max is {max_steps}",
    )


def _required_tool_args_matched(scenario: ScenarioCase, trace: TraceRun) -> CheckOutcome:
    failures: list[str] = []
    calls = trace.tool_calls()
    for tool_name, required_args in scenario.expected.required_tool_args.items():
        matching_call = next(
            (
                call
                for call in calls
                if call.get("tool_name") == tool_name
                and _dict_contains(call.get("arguments"), required_args)
            ),
            None,
        )
        if matching_call is None:
            failures.append(f"{tool_name} missing required args {required_args}")

    return CheckOutcome(
        name=DeterministicCheck.REQUIRED_TOOL_ARGS_MATCHED,
        passed=not failures,
        reason="required tool arguments matched" if not failures else "; ".join(failures),
    )


def _final_output_exists(trace: TraceRun) -> CheckOutcome:
    exists = bool(trace.final_output and trace.final_output.strip())
    return CheckOutcome(
        name=DeterministicCheck.FINAL_OUTPUT_EXISTS,
        passed=exists,
        reason="final output exists" if exists else "final output is missing",
    )


def _dict_contains(value: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    return all(value.get(key) == expected_value for key, expected_value in expected.items())


class HeuristicSemanticGrader:
    def grade(self, scenario: ScenarioCase, trace: TraceRun) -> SemanticGrade:
        forbidden = [
            tool for tool in scenario.expected.should_not_call_tools if tool in trace.tool_names()
        ]
        if forbidden:
            tool_list = ", ".join(forbidden)
            tool_description_patch = (
                "Only call issue_refund after lookup_order confirms eligibility."
                if tool_list == "issue_refund"
                else f"Only call {tool_list} after lookup tools confirm eligibility."
            )
            return SemanticGrade(
                passed=False,
                score=0.1,
                failure_type="premature_tool_execution",
                severity="high",
                reason=f"{tool_list} called before verification.",
                suggested_fix={
                    "prompt_patch": "Require verification before destructive tool calls.",
                    "tool_description_patch": tool_description_patch,
                    "guardrail_patch": (
                        "Block destructive tools when required identifiers are missing."
                    ),
                },
            )
        return SemanticGrade(passed=True, score=1.0)


class OpenAISemanticGrader:
    def __init__(self, *, client: Any | None = None, model: str = DEFAULT_OPENAI_MODEL) -> None:
        if client is None:
            client = OpenAI()
        self.client = client
        self.model = model

    def grade(self, scenario: ScenarioCase, trace: TraceRun) -> SemanticGrade:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are Agent Anvil's semantic grader. Return a strict structured "
                        "grade for whether the agent satisfied the scenario criteria. Focus on "
                        "tool choice, tool ordering, argument validity, clarification behavior, "
                        "looping, and instruction violations."
                    ),
                },
                {
                    "role": "user",
                    "content": _grader_payload(scenario, trace),
                },
            ],
            text_format=SemanticGrade,
        )
        return SemanticGrade.model_validate(response.output_parsed)


def _grader_payload(scenario: ScenarioCase, trace: TraceRun) -> str:
    return (
        "Scenario:\n"
        f"{scenario.model_dump_json(indent=2)}\n\n"
        "Trace:\n"
        f"{trace.model_dump_json(indent=2)}\n\n"
        "Grade the trace against deterministic expectations and semantic success criteria."
    )
