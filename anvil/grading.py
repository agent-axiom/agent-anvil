from __future__ import annotations

import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Protocol

from openai import OpenAI
from pydantic import BaseModel, Field

from anvil.config import DEFAULT_OPENAI_MODEL
from anvil.redaction import redact_payload
from anvil.scenario import PolicyConfig, ScenarioCase, ScenarioDefaults, ToolPrecondition
from anvil.trace import TraceMetrics, TraceRun


class DeterministicCheck(StrEnum):
    TRACE_COMPLETED = "trace_completed"
    EXPECTED_TOOLS_CALLED = "expected_tools_called"
    FORBIDDEN_TOOL_NOT_CALLED = "forbidden_tool_not_called"
    MAX_STEPS_NOT_EXCEEDED = "max_steps_not_exceeded"
    REQUIRED_TOOL_ARGS_MATCHED = "required_tool_args_matched"
    FINAL_OUTPUT_EXISTS = "final_output_exists"
    CLARIFYING_QUESTION_ASKED = "clarifying_question_asked"
    TOOL_POLICY_SATISFIED = "tool_policy_satisfied"
    ASSERTIONS_SATISFIED = "assertions_satisfied"


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


class OpenAISuggestedFix(BaseModel):
    prompt_patch: str
    tool_description_patch: str
    guardrail_patch: str


class OpenAISemanticGrade(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    failure_type: str
    severity: str
    reason: str
    suggested_fix: OpenAISuggestedFix

    def to_semantic_grade(self) -> SemanticGrade:
        return SemanticGrade(
            passed=self.passed,
            score=self.score,
            failure_type=self.failure_type,
            severity=self.severity,
            reason=self.reason,
            suggested_fix=self.suggested_fix.model_dump(),
        )


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
    policies: PolicyConfig | None = None,
) -> DeterministicGrade:
    checks = [
        _trace_completed(trace),
        _expected_tools_called(scenario, trace),
        _forbidden_tools_not_called(scenario, trace),
        _tool_policy_satisfied(trace, policies or PolicyConfig()),
        _max_steps_not_exceeded(scenario, trace, defaults),
        _required_tool_args_matched(scenario, trace),
        _assertions_satisfied(scenario, trace),
        _final_output_exists(trace),
        _clarifying_question_asked(scenario, trace),
    ]
    return DeterministicGrade(passed=all(check.passed for check in checks), checks=checks)


def _trace_completed(trace: TraceRun) -> CheckOutcome:
    return CheckOutcome(
        name=DeterministicCheck.TRACE_COMPLETED,
        passed=trace.status == "completed",
        reason="trace completed"
        if trace.status == "completed"
        else f"trace status is {trace.status}",
    )


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


def _tool_policy_satisfied(trace: TraceRun, policies: PolicyConfig) -> CheckOutcome:
    failures: list[str] = []
    calls = trace.tool_calls()
    for index, call in enumerate(calls):
        tool_name = str(call.get("tool_name", ""))
        if tool_name not in policies.destructive_tools:
            continue

        arguments = call.get("arguments")
        if isinstance(arguments, dict):
            failures.extend(
                f"{tool_name} called with unknown argument {key}"
                for key, value in arguments.items()
                if _is_unknown_value(value)
            )

        failures.extend(
            f"{tool_name} missing prior {precondition.tool}"
            for precondition in policies.require_before.get(tool_name, [])
            if not _prior_precondition_met(calls[:index], precondition)
        )

        if tool_name in policies.require_human_approval:
            failures.append(f"{tool_name} requires human approval")

    return CheckOutcome(
        name=DeterministicCheck.TOOL_POLICY_SATISFIED,
        passed=not failures,
        reason="tool safety policies satisfied" if not failures else "; ".join(failures),
    )


def _prior_precondition_met(
    prior_calls: Sequence[Any],
    precondition: ToolPrecondition,
) -> bool:
    return any(
        call.get("tool_name") == precondition.tool
        and _dict_contains(call.get("result"), precondition.result)
        for call in prior_calls
    )


def _is_unknown_value(value: Any) -> bool:
    return str(value).strip().lower() in {"", "unknown", "none", "null", "n/a", "missing"}


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


def _assertions_satisfied(scenario: ScenarioCase, trace: TraceRun) -> CheckOutcome:
    failures: list[str] = []
    calls = trace.tool_calls()
    tool_names = trace.tool_names()
    final_output = trace.final_output or ""

    for assertion in scenario.expected.assertions:
        failure = _assertion_failure(assertion, calls, tool_names, final_output, trace.metrics)
        if failure:
            failures.append(failure)

    return CheckOutcome(
        name=DeterministicCheck.ASSERTIONS_SATISFIED,
        passed=not failures,
        reason="assertion passed" if not failures else "; ".join(failures),
    )


def _assertion_failure(
    assertion: Any,
    calls: Sequence[Any],
    tool_names: list[str],
    final_output: str,
    metrics: TraceMetrics,
) -> str | None:
    handlers = {
        "tool_called": lambda: _assert_tool_called(assertion.tool, tool_names),
        "tool_not_called": lambda: _assert_tool_not_called(assertion.tool, tool_names),
        "tool_called_before": lambda: _assert_tool_called_before(
            assertion.before,
            assertion.after,
            tool_names,
        ),
        "tool_sequence": lambda: _assert_tool_sequence(assertion.tools, tool_names),
        "min_tool_calls": lambda: _assert_min_tool_calls(
            assertion.tool,
            assertion.count,
            tool_names,
        ),
        "max_tool_calls": lambda: _assert_max_tool_calls(
            assertion.tool,
            assertion.count,
            tool_names,
        ),
        "tool_argument_matches": lambda: _assert_tool_argument_matches(assertion, calls),
        "forbidden_arg_value": lambda: _assert_forbidden_arg_value(assertion, calls),
        "tool_result_matches": lambda: _assert_tool_result_matches(assertion, calls),
        "final_output_contains": lambda: _assert_final_output_contains(
            assertion.text,
            final_output,
        ),
        "final_output_not_contains": lambda: _assert_final_output_not_contains(
            assertion.text,
            final_output,
        ),
        "metric_lte": lambda: _assert_metric_lte(assertion.metric, assertion.value, metrics),
        "metric_gte": lambda: _assert_metric_gte(assertion.metric, assertion.value, metrics),
    }
    return handlers[assertion.type]()


def _assert_tool_called(tool_name: str | None, tool_names: list[str]) -> str | None:
    if tool_name not in tool_names:
        return f"{tool_name} was not called"
    return None


def _assert_tool_not_called(tool_name: str | None, tool_names: list[str]) -> str | None:
    if tool_name in tool_names:
        return f"{tool_name} was called"
    return None


def _assert_tool_called_before(
    before: str | None,
    after: str | None,
    tool_names: list[str],
) -> str | None:
    before_index = _first_tool_index(tool_names, before)
    after_index = _first_tool_index(tool_names, after)
    if before_index is None:
        return f"{before} was not called"
    if after_index is None:
        return f"{after} was not called"
    if after_index >= before_index:
        return f"{after} was not called before {before}"
    return None


def _assert_tool_sequence(expected_tools: list[str], tool_names: list[str]) -> str | None:
    if tool_names == expected_tools:
        return None
    return (
        "tool sequence expected "
        f"{_format_tool_sequence(expected_tools)}, got {_format_tool_sequence(tool_names)}"
    )


def _assert_max_tool_calls(
    tool_name: str | None,
    count: int | None,
    tool_names: list[str],
) -> str | None:
    observed = sum(1 for observed_tool in tool_names if observed_tool == tool_name)
    if count is not None and observed > count:
        return f"{tool_name} called {observed} times, max is {count}"
    return None


def _assert_min_tool_calls(
    tool_name: str | None,
    count: int | None,
    tool_names: list[str],
) -> str | None:
    observed = sum(1 for observed_tool in tool_names if observed_tool == tool_name)
    if count is not None and observed < count:
        return f"{tool_name} called {observed} times, min is {count}"
    return None


def _assert_tool_argument_matches(assertion: Any, calls: Sequence[Any]) -> str | None:
    matching_call = next((call for call in calls if call.get("tool_name") == assertion.tool), None)
    value = (
        _json_path_get(matching_call.get("arguments"), assertion.path or "$")
        if matching_call is not None
        else None
    )
    if value != assertion.equals:
        return (
            f"{assertion.tool} argument {assertion.path} "
            f"expected {assertion.equals!r}, got {value!r}"
        )
    return None


def _assert_forbidden_arg_value(assertion: Any, calls: Sequence[Any]) -> str | None:
    for call in calls:
        if call.get("tool_name") != assertion.tool:
            continue
        value = _json_path_get(call.get("arguments"), assertion.path or "$")
        if value in assertion.values:
            return f"{assertion.tool} argument {assertion.path} had forbidden value {value!r}"
    return None


def _assert_tool_result_matches(assertion: Any, calls: Sequence[Any]) -> str | None:
    matching_call = next((call for call in calls if call.get("tool_name") == assertion.tool), None)
    value = (
        _json_path_get(matching_call.get("result"), assertion.path or "$")
        if matching_call is not None
        else None
    )
    if value != assertion.equals:
        return (
            f"{assertion.tool} result {assertion.path} expected {assertion.equals!r}, got {value!r}"
        )
    return None


def _assert_final_output_contains(text: str | None, final_output: str) -> str | None:
    expected_text = text or ""
    if expected_text.lower() not in final_output.lower():
        return f"final output does not contain {expected_text!r}"
    return None


def _assert_final_output_not_contains(text: str | None, final_output: str) -> str | None:
    forbidden_text = text or ""
    if forbidden_text.lower() in final_output.lower():
        return f"final output contains forbidden text {forbidden_text!r}"
    return None


def _assert_metric_lte(
    metric_name: str | None,
    value: float | None,
    metrics: TraceMetrics,
) -> str | None:
    observed = _trace_metric_value(metrics, metric_name)
    if value is not None and observed > value:
        return (
            f"metric {metric_name} expected <= {_format_number(value)}, "
            f"got {_format_number(observed)}"
        )
    return None


def _assert_metric_gte(
    metric_name: str | None,
    value: float | None,
    metrics: TraceMetrics,
) -> str | None:
    observed = _trace_metric_value(metrics, metric_name)
    if value is not None and observed < value:
        return (
            f"metric {metric_name} expected >= {_format_number(value)}, "
            f"got {_format_number(observed)}"
        )
    return None


def _trace_metric_value(metrics: TraceMetrics, metric_name: str | None) -> float:
    if metric_name is None:
        return 0.0
    return float(getattr(metrics, metric_name))


def _format_number(value: float) -> str:
    return f"{value:g}"


def _first_tool_index(tool_names: list[str], tool_name: str | None) -> int | None:
    if tool_name is None:
        return None
    try:
        return tool_names.index(tool_name)
    except ValueError:
        return None


def _format_tool_sequence(tool_names: list[str]) -> str:
    return " -> ".join(tool_names) if tool_names else "<none>"


def _json_path_get(value: Any, path: str) -> Any:
    if path == "$":
        return value
    if not path.startswith("$."):
        return None
    selected = value
    for part in path[2:].split("."):
        if not isinstance(selected, dict):
            return None
        selected = selected.get(part)
    return selected


def _final_output_exists(trace: TraceRun) -> CheckOutcome:
    exists = bool(trace.final_output and trace.final_output.strip())
    return CheckOutcome(
        name=DeterministicCheck.FINAL_OUTPUT_EXISTS,
        passed=exists,
        reason="final output exists" if exists else "final output is missing",
    )


def _clarifying_question_asked(scenario: ScenarioCase, trace: TraceRun) -> CheckOutcome:
    if not scenario.expected.should_ask_clarifying_question:
        return CheckOutcome(
            name=DeterministicCheck.CLARIFYING_QUESTION_ASKED,
            passed=True,
            reason="clarifying question not required",
        )

    text = " ".join(
        str(part)
        for part in [
            trace.final_output or "",
            *[
                step.get("output_text", "")
                for step in trace.steps
                if step.get("type") == "model_call"
            ],
        ]
    ).lower()
    asks_for_info = any(
        cue in text
        for cue in [
            "?",
            "please provide",
            "please send",
            "send me",
            "provide",
            "share",
            "can you",
            "could you",
            "i need",
        ]
    )
    asks_for_identity = any(
        keyword in text
        for keyword in [
            "email",
            "phone",
            "order number",
            "order id",
            "identity",
            "lookup information",
            "customer id",
            "contact",
        ]
    )
    passed = asks_for_info and asks_for_identity
    return CheckOutcome(
        name=DeterministicCheck.CLARIFYING_QUESTION_ASKED,
        passed=passed,
        reason="clarifying question asked"
        if passed
        else "missing clarifying question for identity or lookup information",
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
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str = DEFAULT_OPENAI_MODEL,
        redact: bool = True,
        redaction_patterns: list[str] | None = None,
    ) -> None:
        if client is None:
            client = OpenAI()
        self.client = client
        self.model = model
        self.redact = redact
        self.redaction_patterns = redaction_patterns or []

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
                        "looping, and instruction violations. For passing traces, use "
                        "failure_type='none', severity='none', an empty reason, and empty "
                        "strings for all suggested_fix fields. For failing traces, fill every "
                        "suggested_fix field with a concrete prompt, tool description, or "
                        "guardrail patch."
                    ),
                },
                {
                    "role": "user",
                    "content": _grader_payload(
                        scenario,
                        trace,
                        redact=self.redact,
                        redaction_patterns=self.redaction_patterns,
                    ),
                },
            ],
            text_format=OpenAISemanticGrade,
        )
        return OpenAISemanticGrade.model_validate(response.output_parsed).to_semantic_grade()


def _grader_payload(
    scenario: ScenarioCase,
    trace: TraceRun,
    *,
    redact: bool = True,
    redaction_patterns: list[str] | None = None,
) -> str:
    scenario_payload: Any = scenario.model_dump(mode="json")
    trace_payload: Any = trace.model_dump(mode="json")
    if redact:
        scenario_payload = redact_payload(scenario_payload, patterns=redaction_patterns)
        trace_payload = redact_payload(trace_payload, patterns=redaction_patterns)

    return (
        "Scenario:\n"
        f"{json.dumps(scenario_payload, indent=2)}\n\n"
        "Trace:\n"
        f"{json.dumps(trace_payload, indent=2)}\n\n"
        "Grade the trace against deterministic expectations and semantic success criteria."
    )
