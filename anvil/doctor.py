from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict

from anvil.conformance import run_external_agent_conformance
from anvil.scenario import ExternalAgentConfig, ScenarioSuite, load_scenario_file

DOCTOR_REPORT_SCHEMA_VERSION = "anvil.doctor.report.v1"


class DoctorCheckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    message: str
    hint: str | None = None


class DoctorReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["anvil.doctor.report.v1"] = DOCTOR_REPORT_SCHEMA_VERSION
    passed: bool
    checks: list[DoctorCheckPayload]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    passed: bool
    message: str
    hint: str | None = None


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
    skip_workflow: bool = False,
) -> DoctorReport:
    checks: list[DoctorCheck] = []
    suite = _load_suite(scenario_path, checks)
    if suite is not None:
        checks.append(_agent_config_check(suite))
        if not skip_conformance:
            checks.append(_conformance_check(suite, max_steps=max_steps))
        if not skip_workflow:
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
        if check.hint:
            lines.append(f"  Hint: {check.hint}")
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
        "| Check | Result | Detail | Hint |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        check_status = "PASS" if check.passed else "FAIL"
        lines.append(
            f"| {_escape_table_cell(check.name)} | {check_status} | "
            f"{_escape_table_cell(check.message)} | "
            f"{_escape_table_cell(check.hint or '')} |"
        )
    return "\n".join(lines) + "\n"


def write_doctor_json(report: DoctorReport, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_doctor_json(report), encoding="utf-8")
    return out_path


def doctor_report_payload(report: DoctorReport) -> dict[str, Any]:
    return {
        "schema_version": DOCTOR_REPORT_SCHEMA_VERSION,
        "passed": report.passed,
        "checks": [_doctor_check_payload(check) for check in report.checks],
    }


def _doctor_check_payload(check: DoctorCheck) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": check.name,
        "passed": check.passed,
        "message": check.message,
    }
    if check.hint:
        payload["hint"] = check.hint
    return payload


def _load_suite(scenario_path: Path, checks: list[DoctorCheck]) -> ScenarioSuite | None:
    try:
        suite = load_scenario_file(scenario_path)
    except Exception as error:
        checks.append(
            DoctorCheck(
                name="scenario_file",
                passed=False,
                message=f"could not load scenario: {error}",
                hint=(
                    "Fix the YAML and validate it with `uv run anvil schema export --out schemas`."
                ),
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
        hint=(
            "Use an external JSONL or HTTP agent in the scenario, or run the eval "
            "directly with `uv run anvil run` for bundled demo agents."
        ),
    )


def _conformance_check(suite: ScenarioSuite, *, max_steps: int) -> DoctorCheck:
    if not isinstance(suite.agent, ExternalAgentConfig):
        return DoctorCheck(
            name="external_agent_conformance",
            passed=False,
            message="agent is not configured with external protocol settings",
            hint="Configure `agent.protocol: jsonl` or `agent.protocol: http` in the scenario.",
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
        hint=(
            "Run `uv run anvil conformance external-agent` with the same command or URL "
            "and inspect the emitted protocol events."
        ),
    )


def _workflow_check(workflow_path: Path, *, scenario_path: Path) -> DoctorCheck:
    if not workflow_path.exists():
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message=f"workflow file does not exist: {workflow_path.as_posix()}",
            hint=(
                "Create it with `uv run anvil init --profile ci-safe`, or pass "
                "--workflow to an existing Agent Anvil workflow."
            ),
        )
    text = workflow_path.read_text(encoding="utf-8")
    workflow = _load_workflow_yaml(text)
    if workflow is None:
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message="could not parse workflow YAML",
            hint="Fix the GitHub Actions YAML syntax and rerun `uv run anvil doctor`.",
        )
    action_steps = _agent_anvil_action_steps(workflow)
    if not action_steps:
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message="workflow does not contain an Agent Anvil action step",
            hint=(
                "Add `uses: agent-axiom/agent-anvil-action@v1.0.2` to the workflow "
                "or regenerate it with `uv run anvil init --profile ci-safe`."
            ),
        )
    scenario_ref = scenario_path.as_posix()
    action_configuration_failure = _workflow_action_configuration_failure(
        workflow,
        action_steps=action_steps,
        scenario_ref=scenario_ref,
    )
    if action_configuration_failure is not None:
        return action_configuration_failure
    return DoctorCheck(
        name="github_workflow",
        passed=True,
        message="workflow references Agent Anvil and the scenario file",
    )


def _load_workflow_yaml(text: str) -> dict[str, Any] | None:
    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return workflow if isinstance(workflow, dict) else None


def _agent_anvil_action_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step for step in _workflow_steps(workflow) if _is_agent_anvil_action_ref(step.get("uses"))
    ]


def _workflow_action_configuration_failure(
    workflow: dict[str, Any],
    *,
    action_steps: list[dict[str, Any]],
    scenario_ref: str,
) -> DoctorCheck | None:
    if not _agent_anvil_jobs_have_checkout_before_action(workflow):
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message="workflow should check out the repository before Agent Anvil runs",
            hint="Add `- uses: actions/checkout@v6` before the Agent Anvil action step.",
        )
    if not any(_step_scenario_ref(step) == scenario_ref for step in action_steps):
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message=f"Agent Anvil action step does not reference scenario {scenario_ref}",
            hint=(
                "Update the action `scenario` input or regenerate the workflow with "
                "`uv run anvil init --profile ci-safe`."
            ),
        )
    if _post_pr_comment_requested(action_steps) and not _workflow_allows_pull_request_comments(
        workflow
    ):
        return DoctorCheck(
            name="github_workflow",
            passed=False,
            message="post-pr-comment requires pull-requests: write permission",
            hint=(
                "Add workflow permissions:\npermissions:\n  contents: read\n  pull-requests: write"
            ),
        )
    return None


def _agent_anvil_action_jobs(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return []
    action_jobs: list[dict[str, Any]] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        job_steps = job.get("steps")
        if not isinstance(job_steps, list):
            continue
        if any(
            isinstance(step, dict) and _is_agent_anvil_action_ref(step.get("uses"))
            for step in job_steps
        ):
            action_jobs.append(job)
    return action_jobs


def _agent_anvil_jobs_have_checkout_before_action(workflow: dict[str, Any]) -> bool:
    return all(
        _job_has_checkout_before_agent_anvil(job) for job in _agent_anvil_action_jobs(workflow)
    )


def _job_has_checkout_before_agent_anvil(job: dict[str, Any]) -> bool:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    checkout_seen = False
    for step in steps:
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if _is_checkout_ref(uses):
            checkout_seen = True
        if _is_agent_anvil_action_ref(uses):
            return checkout_seen
    return False


def _workflow_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return []
    steps: list[dict[str, Any]] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        job_steps = job.get("steps")
        if not isinstance(job_steps, list):
            continue
        steps.extend(step for step in job_steps if isinstance(step, dict))
    return steps


def _is_agent_anvil_action_ref(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("agent-axiom/agent-anvil-action@") or value.startswith(
        "agent-axiom/agent-anvil@"
    )


def _is_checkout_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("actions/checkout@")


def _step_scenario_ref(step: dict[str, Any]) -> str | None:
    inputs = step.get("with")
    if not isinstance(inputs, dict):
        return None
    scenario = inputs.get("scenario")
    return scenario if isinstance(scenario, str) else None


def _post_pr_comment_requested(action_steps: list[dict[str, Any]]) -> bool:
    for step in action_steps:
        inputs = step.get("with")
        if not isinstance(inputs, dict):
            continue
        if inputs.get("post-pr-comment") == "true":
            return True
    return False


def _workflow_allows_pull_request_comments(workflow: dict[str, Any]) -> bool:
    if _permissions_allow_pull_request_write(workflow.get("permissions")):
        return True
    return any(
        _permissions_allow_pull_request_write(job.get("permissions"))
        for job in _agent_anvil_action_jobs(workflow)
    )


def _permissions_allow_pull_request_write(permissions: object) -> bool:
    if isinstance(permissions, str):
        return permissions == "write-all"
    if not isinstance(permissions, dict):
        return False
    permission_map = cast(dict[str, object], permissions)
    return permission_map.get("pull-requests") == "write"


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
