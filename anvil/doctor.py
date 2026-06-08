from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anvil.conformance import run_external_agent_conformance
from anvil.scenario import ExternalAgentConfig, ScenarioSuite, load_scenario_file


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class DoctorReport:
    passed: bool
    checks: tuple[DoctorCheck, ...]


def run_doctor(
    scenario_path: Path,
    *,
    workflow_path: Path,
    max_steps: int = 8,
    skip_conformance: bool = False,
) -> DoctorReport:
    checks: list[DoctorCheck] = []
    suite = _load_suite(scenario_path, checks)
    if suite is not None:
        checks.append(_agent_config_check(suite))
        if not skip_conformance:
            checks.append(_conformance_check(suite, max_steps=max_steps))
        checks.append(_workflow_check(workflow_path, scenario_path=scenario_path))
    return DoctorReport(
        passed=all(check.passed for check in checks),
        checks=tuple(checks),
    )


def render_doctor_report(report: DoctorReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines: list[str] = [f"Agent Anvil doctor: {status}"]
    for check in report.checks:
        check_status = "PASS" if check.passed else "FAIL"
        lines.append(f"- {check.name}: {check_status} - {check.message}")
    return "\n".join(lines)


def render_doctor_json(report: DoctorReport) -> str:
    return json.dumps(doctor_report_payload(report), indent=2) + "\n"


def render_doctor_github_summary(report: DoctorReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines: list[str] = [
        "# Agent Anvil Doctor",
        "",
        f"Status: {status}",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report.checks:
        check_status = "PASS" if check.passed else "FAIL"
        lines.append(
            f"| {_escape_table_cell(check.name)} | {check_status} | "
            f"{_escape_table_cell(check.message)} |"
        )
    return "\n".join(lines) + "\n"


def write_doctor_json(report: DoctorReport, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_doctor_json(report), encoding="utf-8")
    return out_path


def doctor_report_payload(report: DoctorReport) -> dict[str, Any]:
    return {
        "passed": report.passed,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "message": check.message,
            }
            for check in report.checks
        ],
    }


def _load_suite(scenario_path: Path, checks: list[DoctorCheck]) -> ScenarioSuite | None:
    try:
        suite = load_scenario_file(scenario_path)
    except Exception as error:
        checks.append(
            DoctorCheck(
                name="scenario_file",
                passed=False,
                message=f"could not load scenario: {error}",
            )
        )
        return None
    checks.append(
        DoctorCheck(
            name="scenario_file",
            passed=True,
            message=f"loaded {scenario_path.as_posix()}",
        )
    )
    return suite


def _agent_config_check(suite: ScenarioSuite) -> DoctorCheck:
    if isinstance(suite.agent, ExternalAgentConfig):
        target = suite.agent.command if suite.agent.protocol == "jsonl" else suite.agent.url
        return DoctorCheck(
            name="agent_target",
            passed=True,
            message=f"{suite.agent.protocol} target configured: {target}",
        )
    return DoctorCheck(
        name="agent_target",
        passed=False,
        message="scenario uses bundled Python agent; doctor currently checks external agents",
    )


def _conformance_check(suite: ScenarioSuite, *, max_steps: int) -> DoctorCheck:
    if not isinstance(suite.agent, ExternalAgentConfig):
        return DoctorCheck(
            name="external_agent_conformance",
            passed=False,
            message="agent is not configured with external protocol settings",
        )
    result = run_external_agent_conformance(suite.agent, max_steps=max_steps)
    if result.passed:
        return DoctorCheck(
            name="external_agent_conformance",
            passed=True,
            message="external agent protocol conformance passed",
        )
    failed = [check for check in result.checks if not check.passed]
    detail = failed[0].message if failed else "conformance failed"
    return DoctorCheck(
        name="external_agent_conformance",
        passed=False,
        message=detail,
    )


def _workflow_check(workflow_path: Path, *, scenario_path: Path) -> DoctorCheck:
    if not workflow_path.exists():
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message=f"workflow file does not exist: {workflow_path.as_posix()}",
        )
    text = workflow_path.read_text(encoding="utf-8")
    if "agent-axiom/agent-anvil" not in text:
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message="workflow does not reference the Agent Anvil action",
        )
    if scenario_path.as_posix() not in text:
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message=f"workflow does not reference scenario {scenario_path.as_posix()}",
        )
    return DoctorCheck(
        name="github_workflow",
        passed=True,
        message="workflow references Agent Anvil and the scenario file",
    )


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
