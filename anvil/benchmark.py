from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from anvil.grading import DeterministicCheck, GradeResult, SemanticGrader
from anvil.runner import default_semantic_grader, run_suite
from anvil.trace import TraceRun


class BenchmarkOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    json_path: Path = Field(default=Path("docs/paper/results.json"), alias="json")
    markdown: Path = Path("docs/paper/results.md")


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    suites: list[Path] = Field(min_length=1)
    output: BenchmarkOutput = Field(default_factory=BenchmarkOutput)


class BaselineOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    reason: str


class BenchmarkTrialResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    scenario_id: str
    trial: int
    trace_path: Path
    final_answer_passed: bool
    final_answer_reason: str
    trace_aware_passed: bool
    deterministic_passed: bool
    semantic_passed: bool
    failure_type: str
    severity: str


class BenchmarkSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    run_dir: Path
    total_trials: int
    final_answer_passed: int
    trace_aware_passed: int
    final_answer_pass_rate: float
    trace_aware_pass_rate: float


class BenchmarkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    total_suites: int
    total_trials: int
    final_answer_passed: int
    trace_aware_passed: int
    final_answer_pass_rate: float
    trace_aware_pass_rate: float
    answer_only_missed_failures: int
    suites: list[BenchmarkSuiteResult]
    trials: list[BenchmarkTrialResult]


class FinalAnswerBaseline:
    failure_terms = (
        "traceback",
        "exception",
        "failed",
        "error:",
        "tool error",
        "protocol error",
    )

    def grade(self, trace: TraceRun) -> BaselineOutcome:
        final_output = (trace.final_output or "").strip()
        if not final_output:
            return BaselineOutcome(passed=False, reason="final output missing")

        lowered = final_output.lower()
        failure_terms = [term for term in self.failure_terms if term in lowered]
        if failure_terms:
            return BaselineOutcome(
                passed=False,
                reason=f"final output contains failure terms: {', '.join(failure_terms)}",
            )

        return BaselineOutcome(passed=True, reason="final answer present without obvious errors")


def run_benchmark(
    manifest_path: str | Path,
    *,
    offline: bool = False,
    runs_dir: str | Path = "runs/bench",
    out_json: str | Path | None = None,
    out_markdown: str | Path | None = None,
    semantic_grader: SemanticGrader | None = None,
    agent_mode: str | None = None,
    redact: bool | None = None,
) -> BenchmarkResult:
    manifest = load_benchmark_manifest(manifest_path)
    grader = semantic_grader or default_semantic_grader(offline=offline, redact=redact)
    baseline = FinalAnswerBaseline()
    suite_results: list[BenchmarkSuiteResult] = []
    trial_results: list[BenchmarkTrialResult] = []

    for suite_path in manifest.suites:
        suite_run = run_suite(
            suite_path,
            runs_dir=runs_dir,
            semantic_grader=grader,
            agent_mode=agent_mode,
        )
        suite_trials: list[BenchmarkTrialResult] = []
        for grade in suite_run.grades:
            trace = _load_trace(grade.trace_path)
            baseline_outcome = baseline.grade(trace)
            failure_type, severity = _grade_failure_key(grade)
            trial_result = BenchmarkTrialResult(
                suite=suite_run.suite_name,
                scenario_id=grade.scenario_id,
                trial=grade.trial,
                trace_path=Path(grade.trace_path),
                final_answer_passed=baseline_outcome.passed,
                final_answer_reason=baseline_outcome.reason,
                trace_aware_passed=grade.passed,
                deterministic_passed=grade.deterministic_passed,
                semantic_passed=grade.semantic.passed,
                failure_type=failure_type,
                severity=severity,
            )
            suite_trials.append(trial_result)
            trial_results.append(trial_result)

        suite_results.append(
            BenchmarkSuiteResult(
                suite=suite_run.suite_name,
                run_dir=suite_run.run_dir,
                total_trials=len(suite_trials),
                final_answer_passed=sum(1 for trial in suite_trials if trial.final_answer_passed),
                trace_aware_passed=sum(1 for trial in suite_trials if trial.trace_aware_passed),
                final_answer_pass_rate=_pass_rate(
                    sum(1 for trial in suite_trials if trial.final_answer_passed),
                    len(suite_trials),
                ),
                trace_aware_pass_rate=_pass_rate(
                    sum(1 for trial in suite_trials if trial.trace_aware_passed),
                    len(suite_trials),
                ),
            )
        )

    final_answer_passed = sum(1 for trial in trial_results if trial.final_answer_passed)
    trace_aware_passed = sum(1 for trial in trial_results if trial.trace_aware_passed)
    result = BenchmarkResult(
        name=manifest.name,
        description=manifest.description,
        total_suites=len(suite_results),
        total_trials=len(trial_results),
        final_answer_passed=final_answer_passed,
        trace_aware_passed=trace_aware_passed,
        final_answer_pass_rate=_pass_rate(final_answer_passed, len(trial_results)),
        trace_aware_pass_rate=_pass_rate(trace_aware_passed, len(trial_results)),
        answer_only_missed_failures=sum(
            1
            for trial in trial_results
            if trial.final_answer_passed and not trial.trace_aware_passed
        ),
        suites=suite_results,
        trials=trial_results,
    )

    selected_json_path = Path(out_json) if out_json is not None else manifest.output.json_path
    selected_markdown_path = (
        Path(out_markdown) if out_markdown is not None else manifest.output.markdown
    )
    write_benchmark_result(
        result,
        json_path=selected_json_path,
        markdown_path=selected_markdown_path,
    )
    return result


def write_benchmark_result(
    result: BenchmarkResult,
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_benchmark_markdown(result), encoding="utf-8")


def render_benchmark_markdown(result: BenchmarkResult) -> str:
    lines = [
        "# Agent Anvil Paper Benchmark",
        "",
        f"Benchmark: {result.name}",
    ]
    if result.description:
        lines.extend(["", result.description])
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Total suites: {result.total_suites}",
            f"- Total trials: {result.total_trials}",
            f"- Final-answer baseline pass rate: {result.final_answer_pass_rate:.1f}%",
            f"- Trace-aware Agent Anvil pass rate: {result.trace_aware_pass_rate:.1f}%",
            f"- Answer-only missed failures: {result.answer_only_missed_failures}",
            "",
            "## Suite Results",
            "",
            "| Suite | Trials | Final-answer pass rate | Trace-aware pass rate | Run |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    lines.extend(
        [
            f"| {suite.suite} | {suite.total_trials} | "
            f"{suite.final_answer_pass_rate:.1f}% | {suite.trace_aware_pass_rate:.1f}% | "
            f"`{suite.run_dir}` |"
            for suite in result.suites
        ]
    )
    lines.extend(
        [
            "",
            "## Answer-Only Missed Failures",
            "",
        ]
    )
    missed = [
        trial
        for trial in result.trials
        if trial.final_answer_passed and not trial.trace_aware_passed
    ]
    if not missed:
        lines.append("None.")
    else:
        lines.extend(
            [
                f"- `{trial.scenario_id}` trial {trial.trial}: "
                f"{trial.failure_type} / {trial.severity}; trace `{trial.trace_path}`"
                for trial in missed
            ]
        )
    lines.append("")
    return "\n".join(lines)


def load_benchmark_manifest(path: str | Path) -> BenchmarkManifest:
    manifest_path = Path(path)
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = BenchmarkManifest.model_validate(payload)
    return manifest.model_copy(
        update={
            "suites": [_resolve_manifest_path(manifest_path, suite) for suite in manifest.suites],
            "output": manifest.output.model_copy(
                update={
                    "json_path": _resolve_manifest_path(
                        manifest_path,
                        manifest.output.json_path,
                    ),
                    "markdown": _resolve_manifest_path(
                        manifest_path,
                        manifest.output.markdown,
                    ),
                },
            ),
        },
    )


def _resolve_manifest_path(manifest_path: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return manifest_path.parent / value


def _load_trace(path: str | Path) -> TraceRun:
    return TraceRun.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _grade_failure_key(grade: GradeResult) -> tuple[str, str]:
    if grade.passed:
        return "none", "none"
    if grade.semantic.failure_type != "none":
        return grade.semantic.failure_type, grade.semantic.severity
    failed_checks = [check for check in grade.deterministic_checks if not check.passed]
    if not failed_checks:
        return "unknown_failure", "medium"
    check = failed_checks[0]
    return check.name.value, _deterministic_severity(check.name)


def _deterministic_severity(check: DeterministicCheck) -> str:
    if check in {
        DeterministicCheck.TRACE_COMPLETED,
        DeterministicCheck.FORBIDDEN_TOOL_NOT_CALLED,
        DeterministicCheck.REQUIRED_TOOL_ARGS_MATCHED,
        DeterministicCheck.FINAL_OUTPUT_EXISTS,
        DeterministicCheck.TOOL_POLICY_SATISFIED,
        DeterministicCheck.ASSERTIONS_SATISFIED,
    }:
        return "high"
    return "medium"


def _pass_rate(passed: int, total: int) -> float:
    return round((passed / total * 100) if total else 0.0, 1)
