from __future__ import annotations

import os
from dataclasses import dataclass
from inspect import Parameter, signature
from pathlib import Path
from typing import cast

from anvil.agent import AgentRunner, load_agent_runner
from anvil.clustering import FailureCluster, cluster_failures
from anvil.config import AnvilSettings
from anvil.flakiness import FlakyScenario, detect_flaky_scenarios
from anvil.grading import (
    GradeResult,
    HeuristicSemanticGrader,
    OpenAISemanticGrader,
    SemanticGrader,
    deterministic_grade_trace,
)
from anvil.report import render_markdown_report
from anvil.scenario import load_scenario_file
from anvil.storage import (
    create_run_dir,
    load_results,
    update_latest_link,
    write_results,
    write_trace,
)
from anvil.trace import TraceRun


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    suite_name: str
    total_scenarios: int
    total_trials: int
    passed_trials: int
    pass_rate: float
    grades: list[GradeResult]
    clusters: list[FailureCluster]


@dataclass(frozen=True)
class FailureDelta:
    failure_type: str
    severity: str
    baseline_count: int
    latest_count: int


@dataclass(frozen=True)
class SeverityChange:
    failure_type: str
    baseline_severity: str
    latest_severity: str


@dataclass(frozen=True)
class ScenarioRegression:
    scenario_id: str
    baseline_pass_rate: float
    latest_pass_rate: float
    delta: float


@dataclass(frozen=True)
class CompareResult:
    baseline_pass_rate: float
    latest_pass_rate: float
    delta: float
    new_failures: list[FailureDelta]
    resolved_failures: list[FailureDelta]
    severity_changes: list[SeverityChange]
    scenario_regressions: list[ScenarioRegression]
    scenario_improvements: list[ScenarioRegression]
    new_flaky_scenarios: list[FlakyScenario]
    resolved_flaky_scenarios: list[FlakyScenario]


class OpenAIKeyMissingError(RuntimeError):
    pass


def run_suite(
    scenario_file: str | Path,
    *,
    runs_dir: str | Path = "runs",
    trials_override: int | None = None,
    semantic_grader: SemanticGrader | None = None,
    run_id: str | None = None,
    agent_mode: str | None = None,
) -> RunResult:
    suite = load_scenario_file(scenario_file)
    run_dir = create_run_dir(runs_dir, run_id=run_id)
    selected_run_id = run_dir.name
    agent = load_agent_runner(suite.agent)
    grader = semantic_grader or default_semantic_grader()
    selected_agent_mode = agent_mode or AnvilSettings.from_env().agent_mode

    grades: list[GradeResult] = []
    for scenario in suite.scenarios:
        trials = trials_override or scenario.trials(suite.defaults)
        for trial in range(1, trials + 1):
            trace = _run_agent(
                agent,
                input_text=scenario.input,
                scenario_id=scenario.id,
                trial=trial,
                run_id=selected_run_id,
                max_steps=scenario.max_steps(suite.defaults),
                agent_mode=selected_agent_mode,
            )
            trace_path = write_trace(run_dir, trace)
            deterministic = deterministic_grade_trace(
                scenario,
                trace,
                suite.defaults,
                policies=suite.policies,
            )
            semantic = grader.grade(scenario, trace)
            passed = deterministic.passed and semantic.passed
            grades.append(
                GradeResult(
                    scenario_id=scenario.id,
                    trial=trial,
                    passed=passed,
                    deterministic_passed=deterministic.passed,
                    semantic=semantic,
                    trace_path=str(trace_path),
                    deterministic_checks=deterministic.checks,
                )
            )

    clusters = cluster_failures([grade for grade in grades if not grade.passed])
    report = render_markdown_report(
        suite_name=suite.name,
        run_id=selected_run_id,
        total_scenarios=len(suite.scenarios),
        grades=grades,
        clusters=clusters,
    )
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    write_results(
        run_dir=run_dir,
        suite_name=suite.name,
        run_id=selected_run_id,
        total_scenarios=len(suite.scenarios),
        grades=grades,
        clusters=clusters,
    )
    update_latest_link(runs_dir, run_dir)

    passed_trials = sum(1 for grade in grades if grade.passed)
    total_trials = len(grades)
    pass_rate = round((passed_trials / total_trials * 100) if total_trials else 0.0, 1)
    return RunResult(
        run_id=selected_run_id,
        run_dir=run_dir,
        suite_name=suite.name,
        total_scenarios=len(suite.scenarios),
        total_trials=total_trials,
        passed_trials=passed_trials,
        pass_rate=pass_rate,
        grades=grades,
        clusters=clusters,
    )


def default_semantic_grader(
    *,
    offline: bool = False,
    redact: bool | None = None,
) -> SemanticGrader:
    settings = AnvilSettings.from_env()
    if offline or settings.offline:
        return HeuristicSemanticGrader()
    if not os.getenv("OPENAI_API_KEY"):
        msg = (
            "OPENAI_API_KEY is required for OpenAI semantic grading. "
            "Set OPENAI_API_KEY or run with --offline/ANVIL_OFFLINE=true "
            "to use the local heuristic grader."
        )
        raise OpenAIKeyMissingError(msg)
    return OpenAISemanticGrader(
        model=settings.openai_model,
        redact=settings.redact if redact is None else redact,
        redaction_patterns=settings.redaction_patterns,
    )


def regenerate_report(run_dir: str | Path) -> Path:
    payload = load_results(run_dir)
    grades = [GradeResult.model_validate(item) for item in payload["grades"]]
    clusters = [FailureCluster.model_validate(item) for item in payload["clusters"]]
    report = render_markdown_report(
        suite_name=payload["suite"],
        run_id=payload["run_id"],
        total_scenarios=payload["summary"]["total_scenarios"],
        grades=grades,
        clusters=clusters,
    )
    report_path = Path(run_dir) / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def compare_runs(baseline_dir: str | Path, latest_dir: str | Path) -> CompareResult:
    baseline_payload = load_results(baseline_dir)
    latest_payload = load_results(latest_dir)
    baseline = baseline_payload["summary"]
    latest = latest_payload["summary"]
    baseline_rate = float(baseline["pass_rate"])
    latest_rate = float(latest["pass_rate"])

    baseline_failures = _failure_counts(baseline_payload)
    latest_failures = _failure_counts(latest_payload)
    baseline_flaky = _flaky_scenarios(baseline_payload)
    latest_flaky = _flaky_scenarios(latest_payload)
    baseline_flaky_ids = {scenario.scenario_id for scenario in baseline_flaky}
    latest_flaky_ids = {scenario.scenario_id for scenario in latest_flaky}
    failure_keys = set(baseline_failures) | set(latest_failures)
    deltas = [
        FailureDelta(
            failure_type=failure_type,
            severity=severity,
            baseline_count=baseline_failures.get((failure_type, severity), 0),
            latest_count=latest_failures.get((failure_type, severity), 0),
        )
        for failure_type, severity in failure_keys
    ]

    return CompareResult(
        baseline_pass_rate=baseline_rate,
        latest_pass_rate=latest_rate,
        delta=round(latest_rate - baseline_rate, 1),
        new_failures=sorted(
            [delta for delta in deltas if delta.latest_count > delta.baseline_count],
            key=_failure_delta_sort_key,
        ),
        resolved_failures=sorted(
            [delta for delta in deltas if delta.latest_count < delta.baseline_count],
            key=_failure_delta_sort_key,
        ),
        severity_changes=_severity_changes(baseline_failures, latest_failures),
        scenario_regressions=_scenario_regressions(baseline_payload, latest_payload),
        scenario_improvements=_scenario_improvements(baseline_payload, latest_payload),
        new_flaky_scenarios=[
            scenario for scenario in latest_flaky if scenario.scenario_id not in baseline_flaky_ids
        ],
        resolved_flaky_scenarios=[
            scenario for scenario in baseline_flaky if scenario.scenario_id not in latest_flaky_ids
        ],
    )


def _run_agent(agent: AgentRunner, **kwargs: object) -> TraceRun:
    if _accepts_keyword(agent, "agent_mode"):
        return agent(**kwargs)

    kwargs.pop("agent_mode", None)
    return agent(**kwargs)


def _accepts_keyword(agent: AgentRunner, keyword: str) -> bool:
    parameters = signature(agent).parameters.values()
    return any(
        parameter.kind is Parameter.VAR_KEYWORD or parameter.name == keyword
        for parameter in parameters
    )


def _failure_counts(payload: dict[str, object]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for grade in _payload_grades(payload):
        if grade.get("passed") is True:
            continue
        failure_type, severity = _grade_failure_key(grade)
        key = (failure_type, severity)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _payload_grades(payload: dict[str, object]) -> list[dict[str, object]]:
    grades = payload.get("grades", [])
    if not isinstance(grades, list):
        return []
    return [cast(dict[str, object], grade) for grade in grades if isinstance(grade, dict)]


def _flaky_scenarios(payload: dict[str, object]) -> list[FlakyScenario]:
    grades: list[GradeResult] = []
    for grade in _payload_grades(payload):
        try:
            grades.append(GradeResult.model_validate(grade))
        except ValueError:
            continue
    return detect_flaky_scenarios(grades)


def _grade_failure_key(grade: dict[str, object]) -> tuple[str, str]:
    semantic = grade.get("semantic")
    if isinstance(semantic, dict):
        semantic_payload = cast(dict[str, object], semantic)
        failure_type = str(semantic_payload.get("failure_type") or "none")
        severity = str(semantic_payload.get("severity") or "none")
        if failure_type != "none":
            return failure_type, severity

    deterministic_checks = grade.get("deterministic_checks", [])
    if not isinstance(deterministic_checks, list):
        deterministic_checks = []
    failed_checks: list[str] = []
    for check in deterministic_checks:
        if not isinstance(check, dict):
            continue
        check_payload = cast(dict[str, object], check)
        if check_payload.get("passed") is False:
            failed_checks.append(str(check_payload.get("name")))
    return (failed_checks[0] if failed_checks else "deterministic_failure", "medium")


def _severity_changes(
    baseline_failures: dict[tuple[str, str], int],
    latest_failures: dict[tuple[str, str], int],
) -> list[SeverityChange]:
    baseline_severity = _highest_severity_by_type(baseline_failures)
    latest_severity = _highest_severity_by_type(latest_failures)
    changes: list[SeverityChange] = []
    for failure_type in sorted(set(baseline_severity) & set(latest_severity)):
        if baseline_severity[failure_type] == latest_severity[failure_type]:
            continue
        changes.append(
            SeverityChange(
                failure_type=failure_type,
                baseline_severity=baseline_severity[failure_type],
                latest_severity=latest_severity[failure_type],
            )
        )
    return changes


def _highest_severity_by_type(failures: dict[tuple[str, str], int]) -> dict[str, str]:
    result: dict[str, str] = {}
    for failure_type, severity in failures:
        if _severity_rank(severity) > _severity_rank(result.get(failure_type, "none")):
            result[failure_type] = severity
    return result


def _scenario_regressions(
    baseline_payload: dict[str, object],
    latest_payload: dict[str, object],
) -> list[ScenarioRegression]:
    return _scenario_rate_changes(
        baseline_payload,
        latest_payload,
        include_improvements=False,
    )


def _scenario_improvements(
    baseline_payload: dict[str, object],
    latest_payload: dict[str, object],
) -> list[ScenarioRegression]:
    return _scenario_rate_changes(
        baseline_payload,
        latest_payload,
        include_improvements=True,
    )


def _scenario_rate_changes(
    baseline_payload: dict[str, object],
    latest_payload: dict[str, object],
    *,
    include_improvements: bool,
) -> list[ScenarioRegression]:
    baseline_rates = _scenario_pass_rates(baseline_payload)
    latest_rates = _scenario_pass_rates(latest_payload)
    changes: list[ScenarioRegression] = []
    for scenario_id in sorted(set(baseline_rates) | set(latest_rates)):
        baseline_rate = baseline_rates.get(scenario_id, 0.0)
        latest_rate = latest_rates.get(scenario_id, 0.0)
        if include_improvements and latest_rate <= baseline_rate:
            continue
        if not include_improvements and latest_rate >= baseline_rate:
            continue
        changes.append(
            ScenarioRegression(
                scenario_id=scenario_id,
                baseline_pass_rate=baseline_rate,
                latest_pass_rate=latest_rate,
                delta=round(latest_rate - baseline_rate, 1),
            )
        )
    return changes


def _scenario_pass_rates(payload: dict[str, object]) -> dict[str, float]:
    grouped: dict[str, list[bool]] = {}
    for grade in _payload_grades(payload):
        scenario_id = str(grade.get("scenario_id"))
        grouped.setdefault(scenario_id, []).append(grade.get("passed") is True)
    return {
        scenario_id: round(sum(results) / len(results) * 100, 1)
        for scenario_id, results in grouped.items()
        if results
    }


def _failure_delta_sort_key(delta: FailureDelta) -> tuple[int, str, str]:
    return (-abs(delta.latest_count - delta.baseline_count), delta.failure_type, delta.severity)


def _severity_rank(severity: str) -> int:
    return {
        "none": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }.get(severity, 0)
