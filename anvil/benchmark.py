from __future__ import annotations

import csv
import math
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from anvil.grading import DeterministicCheck, SemanticGrader
from anvil.outcomes import OutcomeCategory, classify_grade
from anvil.runner import default_semantic_grader, run_suite
from anvil.trace import TraceRun, load_trace_artifact


class BenchmarkOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    json_path: Path = Field(default=Path("docs/paper/results.json"), alias="json")
    markdown: Path = Path("docs/paper/results.md")
    tables: Path = Path("docs/paper/tables")


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
    trace_completion_passed: bool
    deterministic_assertions_passed: bool
    policy_checks_passed: bool
    trace_aware_passed: bool
    deterministic_passed: bool
    semantic_passed: bool
    outcome_category: OutcomeCategory
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
    final_answer_pass_rate_ci_low: float
    final_answer_pass_rate_ci_high: float
    trace_aware_pass_rate: float
    trace_aware_pass_rate_ci_low: float
    trace_aware_pass_rate_ci_high: float


class BenchmarkAblationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluator: str
    description: str
    total_trials: int
    passed: int
    pass_rate: float
    pass_rate_ci_low: float
    pass_rate_ci_high: float
    answer_only_missed_failures: int
    answer_only_missed_failure_rate: float


class BenchmarkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    total_suites: int
    total_trials: int
    final_answer_passed: int
    trace_aware_passed: int
    final_answer_pass_rate: float
    final_answer_pass_rate_ci_low: float
    final_answer_pass_rate_ci_high: float
    trace_aware_pass_rate: float
    trace_aware_pass_rate_ci_low: float
    trace_aware_pass_rate_ci_high: float
    answer_only_missed_failures: int
    answer_only_missed_failure_rate: float
    answer_only_missed_failure_rate_ci_low: float
    answer_only_missed_failure_rate_ci_high: float
    outcome_counts: dict[str, int]
    evaluator_ablation: list[BenchmarkAblationResult]
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
            outcome = classify_grade(grade)
            checks_by_name = {check.name: check.passed for check in grade.deterministic_checks}
            trial_result = BenchmarkTrialResult(
                suite=suite_run.suite_name,
                scenario_id=grade.scenario_id,
                trial=grade.trial,
                trace_path=Path(grade.trace_path),
                final_answer_passed=baseline_outcome.passed,
                final_answer_reason=baseline_outcome.reason,
                trace_completion_passed=_trace_completion_passed(checks_by_name),
                deterministic_assertions_passed=_deterministic_assertions_passed(checks_by_name),
                policy_checks_passed=_policy_checks_passed(checks_by_name),
                trace_aware_passed=grade.passed,
                deterministic_passed=grade.deterministic_passed,
                semantic_passed=grade.semantic.passed,
                outcome_category=outcome.category,
                failure_type=outcome.failure_type,
                severity=outcome.severity,
            )
            suite_trials.append(trial_result)
            trial_results.append(trial_result)

        suite_total = len(suite_trials)
        suite_final_answer_passed = sum(1 for trial in suite_trials if trial.final_answer_passed)
        suite_trace_aware_passed = sum(1 for trial in suite_trials if trial.trace_aware_passed)
        suite_final_answer_ci = _pass_rate_interval(suite_final_answer_passed, suite_total)
        suite_trace_aware_ci = _pass_rate_interval(suite_trace_aware_passed, suite_total)
        suite_results.append(
            BenchmarkSuiteResult(
                suite=suite_run.suite_name,
                run_dir=suite_run.run_dir,
                total_trials=suite_total,
                final_answer_passed=suite_final_answer_passed,
                trace_aware_passed=suite_trace_aware_passed,
                final_answer_pass_rate=_pass_rate(suite_final_answer_passed, suite_total),
                final_answer_pass_rate_ci_low=suite_final_answer_ci[0],
                final_answer_pass_rate_ci_high=suite_final_answer_ci[1],
                trace_aware_pass_rate=_pass_rate(suite_trace_aware_passed, suite_total),
                trace_aware_pass_rate_ci_low=suite_trace_aware_ci[0],
                trace_aware_pass_rate_ci_high=suite_trace_aware_ci[1],
            )
        )

    total_trials = len(trial_results)
    final_answer_passed = sum(1 for trial in trial_results if trial.final_answer_passed)
    trace_aware_passed = sum(1 for trial in trial_results if trial.trace_aware_passed)
    answer_only_missed_failures = sum(
        1 for trial in trial_results if trial.final_answer_passed and not trial.trace_aware_passed
    )
    final_answer_ci = _pass_rate_interval(final_answer_passed, total_trials)
    trace_aware_ci = _pass_rate_interval(trace_aware_passed, total_trials)
    missed_failure_ci = _pass_rate_interval(answer_only_missed_failures, total_trials)
    result = BenchmarkResult(
        name=manifest.name,
        description=manifest.description,
        total_suites=len(suite_results),
        total_trials=total_trials,
        final_answer_passed=final_answer_passed,
        trace_aware_passed=trace_aware_passed,
        final_answer_pass_rate=_pass_rate(final_answer_passed, total_trials),
        final_answer_pass_rate_ci_low=final_answer_ci[0],
        final_answer_pass_rate_ci_high=final_answer_ci[1],
        trace_aware_pass_rate=_pass_rate(trace_aware_passed, total_trials),
        trace_aware_pass_rate_ci_low=trace_aware_ci[0],
        trace_aware_pass_rate_ci_high=trace_aware_ci[1],
        answer_only_missed_failures=answer_only_missed_failures,
        answer_only_missed_failure_rate=_pass_rate(answer_only_missed_failures, total_trials),
        answer_only_missed_failure_rate_ci_low=missed_failure_ci[0],
        answer_only_missed_failure_rate_ci_high=missed_failure_ci[1],
        outcome_counts=_outcome_counts(trial_results),
        evaluator_ablation=_evaluator_ablation(trial_results),
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
        tables_dir=manifest.output.tables,
    )
    return result


def write_benchmark_result(
    result: BenchmarkResult,
    *,
    json_path: Path,
    markdown_path: Path,
    tables_dir: Path | None = None,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_benchmark_markdown(result), encoding="utf-8")
    if tables_dir is not None:
        write_benchmark_tables(
            result, tables_dir=tables_dir, index_path=markdown_path.parent / "tables.md"
        )


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
            f"- Final-answer baseline pass rate: {_final_answer_rate_ci(result)}",
            f"- Trace-aware Agent Anvil pass rate: {_trace_aware_rate_ci(result)}",
            f"- Answer-only missed failures: {result.answer_only_missed_failures}",
            f"- Answer-only missed failure rate: {_missed_failure_rate_ci(result)}",
            "",
            "## Outcome Categories",
            "",
            "| Outcome | Trials |",
            "| --- | ---: |",
        ]
    )
    lines.extend(
        [f"| {outcome} | {count} |" for outcome, count in sorted(result.outcome_counts.items())]
    )
    lines.extend(
        [
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
            f"{_final_answer_rate_ci(suite)} | "
            f"{_trace_aware_rate_ci(suite)} | "
            f"`{suite.run_dir}` |"
            for suite in result.suites
        ]
    )
    lines.extend(
        [
            "",
            "## Evaluator Ablation",
            "",
            "| Evaluator | Trials | Pass rate | Answer-only missed failures |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        [
            f"| {entry.evaluator} | {entry.total_trials} | "
            f"{_ablation_rate_ci(entry)} | "
            f"{entry.answer_only_missed_failures} |"
            for entry in result.evaluator_ablation
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
                f"{trial.outcome_category} / {trial.failure_type} / {trial.severity}; "
                f"trace `{trial.trace_path}`"
                for trial in missed
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_benchmark_tables(
    result: BenchmarkResult,
    *,
    tables_dir: Path,
    index_path: Path,
) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        tables_dir / "suite_results.csv",
        [
            "suite",
            "trials",
            "final_answer_pass_rate",
            "final_answer_pass_rate_ci_low",
            "final_answer_pass_rate_ci_high",
            "trace_aware_pass_rate",
            "trace_aware_pass_rate_ci_low",
            "trace_aware_pass_rate_ci_high",
        ],
        [
            [
                suite.suite,
                suite.total_trials,
                f"{suite.final_answer_pass_rate:.1f}",
                f"{suite.final_answer_pass_rate_ci_low:.1f}",
                f"{suite.final_answer_pass_rate_ci_high:.1f}",
                f"{suite.trace_aware_pass_rate:.1f}",
                f"{suite.trace_aware_pass_rate_ci_low:.1f}",
                f"{suite.trace_aware_pass_rate_ci_high:.1f}",
            ]
            for suite in result.suites
        ],
    )
    _write_csv(
        tables_dir / "outcome_counts.csv",
        ["outcome", "trials"],
        [[outcome, count] for outcome, count in sorted(result.outcome_counts.items())],
    )
    _write_csv(
        tables_dir / "evaluator_ablation.csv",
        [
            "evaluator",
            "total_trials",
            "passed",
            "pass_rate",
            "pass_rate_ci_low",
            "pass_rate_ci_high",
            "answer_only_missed_failures",
            "answer_only_missed_failure_rate",
        ],
        [
            [
                entry.evaluator,
                entry.total_trials,
                entry.passed,
                f"{entry.pass_rate:.1f}",
                f"{entry.pass_rate_ci_low:.1f}",
                f"{entry.pass_rate_ci_high:.1f}",
                entry.answer_only_missed_failures,
                f"{entry.answer_only_missed_failure_rate:.1f}",
            ]
            for entry in result.evaluator_ablation
        ],
    )
    missed = [
        trial
        for trial in result.trials
        if trial.final_answer_passed and not trial.trace_aware_passed
    ]
    _write_csv(
        tables_dir / "missed_failures.csv",
        ["suite", "scenario_id", "trial", "outcome", "failure_type", "severity"],
        [
            [
                trial.suite,
                trial.scenario_id,
                trial.trial,
                trial.outcome_category.value,
                trial.failure_type,
                trial.severity,
            ]
            for trial in missed
        ],
    )
    (tables_dir / "suite_results.tex").write_text(
        render_suite_results_latex(result),
        encoding="utf-8",
    )
    (tables_dir / "evaluator_ablation.tex").write_text(
        render_evaluator_ablation_latex(result),
        encoding="utf-8",
    )
    index_path.write_text(render_tables_markdown(result, tables_dir=tables_dir), encoding="utf-8")


def render_tables_markdown(result: BenchmarkResult, *, tables_dir: Path) -> str:
    display_dir = _display_path(tables_dir)
    return "\n".join(
        [
            "# Paper Tables",
            "",
            f"Benchmark: {result.name}",
            "",
            "Generated table artifacts:",
            "",
            f"- `{display_dir / 'suite_results.csv'}`",
            f"- `{display_dir / 'evaluator_ablation.csv'}`",
            f"- `{display_dir / 'outcome_counts.csv'}`",
            f"- `{display_dir / 'missed_failures.csv'}`",
            f"- `{display_dir / 'suite_results.tex'}`",
            f"- `{display_dir / 'evaluator_ablation.tex'}`",
            "",
            "## Main Result",
            "",
            f"- Total trials: {result.total_trials}",
            f"- Final-answer baseline pass rate: {_final_answer_rate_ci(result)}",
            f"- Trace-aware Agent Anvil pass rate: {_trace_aware_rate_ci(result)}",
            f"- Answer-only missed failures: {result.answer_only_missed_failures}",
            f"- Answer-only missed failure rate: {_missed_failure_rate_ci(result)}",
            "",
        ]
    )


def render_evaluator_ablation_latex(result: BenchmarkResult) -> str:
    lines = [
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Evaluator & Trials & Pass rate & Answer-only missed failures \\\\",
        "\\midrule",
    ]
    lines.extend(
        [
            f"{_ablation_label(entry.evaluator)} & {entry.total_trials} & "
            f"{_ablation_latex_ci(entry)} & "
            f"{entry.answer_only_missed_failures} \\\\"
            for entry in result.evaluator_ablation
        ]
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    return "\n".join(lines)


def render_suite_results_latex(result: BenchmarkResult) -> str:
    lines = [
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Suite & Trials & Final-answer pass (95\\% CI) & Trace-aware pass (95\\% CI) \\\\",
        "\\midrule",
    ]
    lines.extend(
        [
            f"{_latex_label(suite.suite)} & {suite.total_trials} & "
            f"{_final_answer_latex_ci(suite)} & "
            f"{_trace_aware_latex_ci(suite)} \\\\"
            for suite in result.suites
        ]
    )
    lines.extend(
        [
            "\\midrule",
            f"Total & {result.total_trials} & "
            f"{_final_answer_latex_ci(result)} & "
            f"{_trace_aware_latex_ci(result)} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "",
        ]
    )
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
                    "tables": _resolve_manifest_path(
                        manifest_path,
                        manifest.output.tables,
                    ),
                },
            ),
        },
    )


def _resolve_manifest_path(manifest_path: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return manifest_path.parent / value


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _latex_label(value: str) -> str:
    suffix = "_trace_suite"
    label = value.removeprefix("paper_")
    if label.endswith(suffix):
        label = label[: -len(suffix)]
    return label.replace("_", "-").title()


def _ablation_label(value: str) -> str:
    return value.replace("_", " ").title()


def _display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path


def _load_trace(path: str | Path) -> TraceRun:
    return load_trace_artifact(path)


def _outcome_counts(trials: list[BenchmarkTrialResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trial in trials:
        outcome = trial.outcome_category.value
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def _evaluator_ablation(trials: list[BenchmarkTrialResult]) -> list[BenchmarkAblationResult]:
    variants: list[tuple[str, str, str]] = [
        (
            "final_answer_baseline",
            "Final answer exists and avoids obvious runtime failure text.",
            "final_answer_passed",
        ),
        (
            "trace_completion_only",
            "Trace completed without protocol/runtime failure.",
            "trace_completion_passed",
        ),
        (
            "deterministic_assertions",
            "Trace completion plus deterministic expectations and assertions, excluding policy.",
            "deterministic_assertions_passed",
        ),
        (
            "policy_checks",
            "Trace completion plus risky-tool policy preconditions.",
            "policy_checks_passed",
        ),
        (
            "full_trace_aware",
            "Full Agent Anvil trace-aware evaluator, including semantic grading.",
            "trace_aware_passed",
        ),
    ]
    return [
        _ablation_result(
            evaluator=evaluator,
            description=description,
            trials=trials,
            passed=[trial for trial in trials if bool(getattr(trial, field))],
        )
        for evaluator, description, field in variants
    ]


def _ablation_result(
    *,
    evaluator: str,
    description: str,
    trials: list[BenchmarkTrialResult],
    passed: list[BenchmarkTrialResult],
) -> BenchmarkAblationResult:
    total = len(trials)
    passed_count = len(passed)
    passed_trial_keys = {(trial.suite, trial.scenario_id, trial.trial) for trial in passed}
    failed_trial_keys = {
        (trial.suite, trial.scenario_id, trial.trial)
        for trial in trials
        if (trial.suite, trial.scenario_id, trial.trial) not in passed_trial_keys
    }
    missed_failures = sum(
        1
        for trial in trials
        if trial.final_answer_passed
        and (trial.suite, trial.scenario_id, trial.trial) in failed_trial_keys
    )
    interval = _pass_rate_interval(passed_count, total)
    return BenchmarkAblationResult(
        evaluator=evaluator,
        description=description,
        total_trials=total,
        passed=passed_count,
        pass_rate=_pass_rate(passed_count, total),
        pass_rate_ci_low=interval[0],
        pass_rate_ci_high=interval[1],
        answer_only_missed_failures=missed_failures,
        answer_only_missed_failure_rate=_pass_rate(missed_failures, total),
    )


def _trace_completion_passed(checks: dict[DeterministicCheck, bool]) -> bool:
    return checks.get(DeterministicCheck.TRACE_COMPLETED, False)


def _deterministic_assertions_passed(checks: dict[DeterministicCheck, bool]) -> bool:
    ignored_checks = {DeterministicCheck.TOOL_POLICY_SATISFIED}
    return all(passed for check, passed in checks.items() if check not in ignored_checks)


def _policy_checks_passed(checks: dict[DeterministicCheck, bool]) -> bool:
    return _trace_completion_passed(checks) and checks.get(
        DeterministicCheck.TOOL_POLICY_SATISFIED,
        True,
    )


def _pass_rate(passed: int, total: int) -> float:
    return round((passed / total * 100) if total else 0.0, 1)


def _final_answer_rate_ci(result: BenchmarkResult | BenchmarkSuiteResult) -> str:
    return format_rate_ci(
        result.final_answer_pass_rate,
        result.final_answer_pass_rate_ci_low,
        result.final_answer_pass_rate_ci_high,
    )


def _trace_aware_rate_ci(result: BenchmarkResult | BenchmarkSuiteResult) -> str:
    return format_rate_ci(
        result.trace_aware_pass_rate,
        result.trace_aware_pass_rate_ci_low,
        result.trace_aware_pass_rate_ci_high,
    )


def _missed_failure_rate_ci(result: BenchmarkResult) -> str:
    return format_rate_ci(
        result.answer_only_missed_failure_rate,
        result.answer_only_missed_failure_rate_ci_low,
        result.answer_only_missed_failure_rate_ci_high,
    )


def _ablation_rate_ci(result: BenchmarkAblationResult) -> str:
    return format_rate_ci(
        result.pass_rate,
        result.pass_rate_ci_low,
        result.pass_rate_ci_high,
    )


def _final_answer_latex_ci(result: BenchmarkResult | BenchmarkSuiteResult) -> str:
    return _format_latex_ci(
        result.final_answer_pass_rate,
        result.final_answer_pass_rate_ci_low,
        result.final_answer_pass_rate_ci_high,
    )


def _trace_aware_latex_ci(result: BenchmarkResult | BenchmarkSuiteResult) -> str:
    return _format_latex_ci(
        result.trace_aware_pass_rate,
        result.trace_aware_pass_rate_ci_low,
        result.trace_aware_pass_rate_ci_high,
    )


def _ablation_latex_ci(result: BenchmarkAblationResult) -> str:
    return _format_latex_ci(
        result.pass_rate,
        result.pass_rate_ci_low,
        result.pass_rate_ci_high,
    )


def _pass_rate_interval(passed: int, total: int) -> tuple[float, float]:
    """Wilson score interval, rendered as percentage points for compact paper tables."""
    if total == 0:
        return (0.0, 0.0)
    z = 1.96
    proportion = passed / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z * math.sqrt((proportion * (1 - proportion) + z**2 / (4 * total)) / total) / denominator
    )
    low = max(0.0, center - margin) * 100
    high = min(1.0, center + margin) * 100
    return (round(low, 1), round(high, 1))


def format_rate_ci(rate: float, low: float, high: float) -> str:
    return f"{rate:.1f}% [95% CI: {low:.1f}%, {high:.1f}%]"


def _format_latex_ci(rate: float, low: float, high: float) -> str:
    return f"{rate:.1f}\\% [{low:.1f}, {high:.1f}]"
