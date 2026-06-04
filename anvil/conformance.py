from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from anvil.agent import run_external_agent
from anvil.scenario import ExternalAgentConfig
from anvil.trace import TraceRun, TraceStep

CONFORMANCE_INPUT = (
    "Agent Anvil external JSONL conformance check. Emit valid JSONL trace events and a "
    "final_output event."
)
CONFORMANCE_SCENARIO_ID = "external_agent_conformance"


@dataclass(frozen=True)
class ConformanceCheck:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class ConformanceResult:
    passed: bool
    trace: TraceRun
    checks: tuple[ConformanceCheck, ...]
    markdown: str


def parse_env_overrides(values: list[str] | None) -> dict[str, str]:
    env: dict[str, str] = {}
    for value in values or []:
        key, separator, env_value = value.partition("=")
        if not separator or not key:
            msg = f"--env must use KEY=VALUE, got: {value}"
            raise ValueError(msg)
        env[key] = env_value
    return env


def run_external_agent_conformance(
    config: ExternalAgentConfig,
    *,
    max_steps: int = 8,
) -> ConformanceResult:
    run_id = f"conformance_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    trace = run_external_agent(
        config,
        input_text=CONFORMANCE_INPUT,
        scenario_id=CONFORMANCE_SCENARIO_ID,
        trial=1,
        run_id=run_id,
        max_steps=max_steps,
    )
    checks = _build_checks(trace, max_steps=max_steps)
    passed = all(check.passed for check in checks)
    return ConformanceResult(
        passed=passed,
        trace=trace,
        checks=tuple(checks),
        markdown=render_conformance_report(trace, checks),
    )


def write_conformance_report(result: ConformanceResult, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.markdown, encoding="utf-8")
    return out_path


def render_conformance_report(trace: TraceRun, checks: list[ConformanceCheck]) -> str:
    status = "PASS" if all(check.passed for check in checks) else "FAIL"
    lines = [
        "# Agent Anvil External Agent Conformance",
        "",
        f"Status: {status}",
        f"Run ID: {trace.run_id}",
        f"Trace status: {trace.status}",
        f"Steps: {len(trace.steps)}",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        result = "PASS" if check.passed else "FAIL"
        lines.append(f"| {check.name} | {result} | {_escape_table_cell(check.message)} |")
    lines.extend(
        [
            "",
            "## Final Output",
            "",
            trace.final_output or "",
            "",
        ]
    )
    return "\n".join(lines)


def _build_checks(trace: TraceRun, *, max_steps: int) -> list[ConformanceCheck]:
    protocol_errors = [step for step in trace.steps if step.get("type") == "agent_protocol_error"]
    final_output_present = bool(trace.final_output) and not protocol_errors
    return [
        ConformanceCheck(
            name="process_completed",
            passed=trace.status == "completed",
            message="trace status is completed" if trace.status == "completed" else trace.status,
        ),
        ConformanceCheck(
            name="no_agent_protocol_error",
            passed=not protocol_errors,
            message="no agent_protocol_error events"
            if not protocol_errors
            else _protocol_error_message(protocol_errors[0]),
        ),
        ConformanceCheck(
            name="max_steps_respected",
            passed=len(trace.steps) <= max_steps,
            message=f"{len(trace.steps)} <= {max_steps}",
        ),
        ConformanceCheck(
            name="final_output_present",
            passed=final_output_present,
            message=_final_output_message(trace.final_output, protocol_errors),
        ),
    ]


def _protocol_error_message(step: object) -> str:
    if isinstance(step, TraceStep):
        step_mapping = step
    elif isinstance(step, Mapping):
        step_mapping = cast("Mapping[str, Any]", step)
    else:
        return "agent_protocol_error"
    error_type = step_mapping.get("error_type", "unknown")
    message = step_mapping.get("message", "")
    return f"agent_protocol_error ({error_type}): {message}"


def _final_output_message(final_output: str | None, protocol_errors: Sequence[object]) -> str:
    if protocol_errors:
        return "final_output unavailable because agent protocol failed"
    if final_output:
        return "final_output event emitted"
    return "missing final_output"


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
