from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from anvil.clustering import FailureCluster, cluster_failures
from anvil.config import AnvilSettings
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

AgentRunner = Callable[..., TraceRun]


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


def run_suite(
    scenario_file: str | Path,
    *,
    runs_dir: str | Path = "runs",
    trials_override: int | None = None,
    semantic_grader: SemanticGrader | None = None,
    run_id: str | None = None,
) -> RunResult:
    suite = load_scenario_file(scenario_file)
    run_dir = create_run_dir(runs_dir, run_id=run_id)
    selected_run_id = run_dir.name
    agent = _load_agent_runner(suite.agent)
    grader = semantic_grader or default_semantic_grader()

    grades: list[GradeResult] = []
    for scenario in suite.scenarios:
        trials = trials_override or scenario.trials(suite.defaults)
        for trial in range(1, trials + 1):
            trace = agent(
                input_text=scenario.input,
                scenario_id=scenario.id,
                trial=trial,
                run_id=selected_run_id,
                max_steps=scenario.max_steps(suite.defaults),
            )
            trace_path = write_trace(run_dir, trace)
            deterministic = deterministic_grade_trace(scenario, trace, suite.defaults)
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


def default_semantic_grader(*, offline: bool = False) -> SemanticGrader:
    settings = AnvilSettings.from_env()
    if offline or settings.offline or not os.getenv("OPENAI_API_KEY"):
        return HeuristicSemanticGrader()
    return OpenAISemanticGrader(model=settings.openai_model)


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


def compare_runs(baseline_dir: str | Path, latest_dir: str | Path) -> dict[str, float]:
    baseline = load_results(baseline_dir)["summary"]
    latest = load_results(latest_dir)["summary"]
    baseline_rate = float(baseline["pass_rate"])
    latest_rate = float(latest["pass_rate"])
    return {
        "baseline_pass_rate": baseline_rate,
        "latest_pass_rate": latest_rate,
        "delta": round(latest_rate - baseline_rate, 1),
    }


def _load_agent_runner(agent_module: str) -> AgentRunner:
    module = importlib.import_module(agent_module)
    return module.run_agent
