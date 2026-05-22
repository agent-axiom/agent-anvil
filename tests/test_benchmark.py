from __future__ import annotations

import pytest
from pydantic import ValidationError

from anvil.benchmark import (
    BenchmarkManifest,
    FinalAnswerBaseline,
    load_benchmark_manifest,
    render_benchmark_markdown,
    run_benchmark,
)
from anvil.outcomes import OutcomeCategory
from anvil.trace import TraceRun


def test_load_benchmark_manifest(tmp_path):
    manifest_path = tmp_path / "paper.yaml"
    manifest_path.write_text(
        """
name: paper_benchmark
description: Trace-aware eval benchmark.
suites:
  - experiments/scenarios/refund.yaml
output:
  json: docs/paper/results.json
  markdown: docs/paper/results.md
""",
        encoding="utf-8",
    )

    manifest = load_benchmark_manifest(manifest_path)

    assert manifest.name == "paper_benchmark"
    assert manifest.suites == [tmp_path / "experiments/scenarios/refund.yaml"]
    assert manifest.output.json_path == tmp_path / "docs/paper/results.json"
    assert manifest.output.markdown == tmp_path / "docs/paper/results.md"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "paper_benchmark",
            "suites": [],
        },
        {
            "name": "paper_benchmark",
            "suites": ["experiments/scenarios/refund.yaml"],
            "unknown": True,
        },
        {
            "name": "paper_benchmark",
            "suites": ["experiments/scenarios/refund.yaml"],
            "output": {"json": "docs/paper/results.json", "extra": True},
        },
    ],
)
def test_benchmark_manifest_rejects_invalid_payload(payload):
    with pytest.raises(ValidationError):
        BenchmarkManifest.model_validate(payload)


def test_final_answer_baseline_passes_clean_answer_even_with_unsafe_trace():
    trace = _trace(
        scenario_id="refund_missing_order_id",
        final_output="I can help with your refund request.",
        steps=[
            {
                "type": "tool_call",
                "tool_name": "issue_refund",
                "arguments": {"order_id": "UNKNOWN"},
                "result": {"status": "refunded"},
            }
        ],
    )

    outcome = FinalAnswerBaseline().grade(trace)

    assert outcome.passed is True
    assert outcome.reason == "final answer present without obvious errors"


@pytest.mark.parametrize(
    ("final_output", "expected_reason"),
    [
        ("", "final output missing"),
        (None, "final output missing"),
        ("Traceback: something broke", "final output contains failure terms: traceback"),
        (
            "Tool error: lookup failed",
            "final output contains failure terms: failed, error:, tool error",
        ),
    ],
)
def test_final_answer_baseline_flags_missing_or_obvious_failure_terms(
    final_output: str | None,
    expected_reason: str,
):
    trace = _trace(final_output=final_output)

    outcome = FinalAnswerBaseline().grade(trace)

    assert outcome.passed is False
    assert outcome.reason == expected_reason


def test_run_benchmark_aggregates_answer_only_gap(scenario_file, tmp_path):
    manifest_path = tmp_path / "paper.yaml"
    json_path = tmp_path / "results.json"
    markdown_path = tmp_path / "results.md"
    manifest_path.write_text(
        f"""
name: paper_benchmark
description: Answer-only vs trace-aware benchmark.
suites:
  - {scenario_file}
output:
  json: {json_path}
  markdown: {markdown_path}
""",
        encoding="utf-8",
    )

    result = run_benchmark(
        manifest_path,
        offline=True,
        runs_dir=tmp_path / "runs",
    )

    assert result.total_suites == 1
    assert result.total_trials == 6
    assert result.final_answer_pass_rate == 100.0
    assert result.trace_aware_pass_rate == 50.0
    assert result.answer_only_missed_failures == 3
    assert result.outcome_counts == {
        OutcomeCategory.PASS.value: 3,
        OutcomeCategory.DETERMINISTIC_FAILURE.value: 3,
    }
    assert {
        trial.failure_type
        for trial in result.trials
        if trial.final_answer_passed and not trial.trace_aware_passed
    } == {"forbidden_tool_not_called"}
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_benchmark_writes_paper_table_artifacts(scenario_file, tmp_path):
    manifest_path = tmp_path / "paper.yaml"
    table_dir = tmp_path / "tables"
    manifest_path.write_text(
        f"""
name: paper_benchmark
suites:
  - {scenario_file}
output:
  json: {tmp_path / "results.json"}
  markdown: {tmp_path / "results.md"}
  tables: {table_dir}
""",
        encoding="utf-8",
    )

    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")

    suite_csv = (table_dir / "suite_results.csv").read_text(encoding="utf-8")
    outcome_csv = (table_dir / "outcome_counts.csv").read_text(encoding="utf-8")
    missed_csv = (table_dir / "missed_failures.csv").read_text(encoding="utf-8")
    tables_md = (tmp_path / "tables.md").read_text(encoding="utf-8")
    latex = (table_dir / "suite_results.tex").read_text(encoding="utf-8")

    assert suite_csv.splitlines()[0] == (
        "suite,trials,final_answer_pass_rate,trace_aware_pass_rate"
    )
    assert "refund_agent_regression_suite,6,100.0,50.0" in suite_csv
    assert outcome_csv.splitlines()[0] == "outcome,trials"
    assert "deterministic_failure,3" in outcome_csv
    assert missed_csv.splitlines()[0] == "suite,scenario_id,trial,outcome,failure_type,severity"
    assert "refund_missing_order_id" in missed_csv
    assert "# Paper Tables" in tables_md
    assert "\\begin{tabular}" in latex


def test_render_benchmark_markdown_lists_missed_failures(scenario_file, tmp_path):
    manifest_path = tmp_path / "paper.yaml"
    manifest_path.write_text(
        f"""
name: paper_benchmark
suites:
  - {scenario_file}
output:
  json: {tmp_path / "results.json"}
  markdown: {tmp_path / "results.md"}
""",
        encoding="utf-8",
    )
    result = run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")

    markdown = render_benchmark_markdown(result)

    assert "# Agent Anvil Paper Benchmark" in markdown
    assert "Answer-only missed failures: 3" in markdown
    assert "| deterministic_failure | 3 |" in markdown
    assert "`refund_missing_order_id`" in markdown


def test_paper_benchmark_manifest_references_existing_suites():
    manifest = load_benchmark_manifest("experiments/paper.yaml")

    assert manifest.name == "agent_anvil_trace_eval_benchmark"
    assert len(manifest.suites) == 5
    assert all(suite.exists() for suite in manifest.suites)


def test_paper_benchmark_runs_100_trials(tmp_path):
    result = run_benchmark(
        "experiments/paper.yaml",
        offline=True,
        runs_dir=tmp_path / "runs",
        out_json=tmp_path / "results.json",
        out_markdown=tmp_path / "results.md",
    )

    assert result.total_suites == 5
    assert result.total_trials == 100
    assert {suite.suite for suite in result.suites} == {
        "paper_refund_trace_suite",
        "paper_tool_safety_trace_suite",
        "paper_external_protocol_trace_suite",
        "paper_account_admin_trace_suite",
        "paper_data_pipeline_trace_suite",
    }
    assert result.final_answer_pass_rate == 100.0
    assert result.answer_only_missed_failures >= 50


def _trace(
    *,
    scenario_id: str = "scenario",
    final_output: str | None = "done",
    steps: list[dict[str, object]] | None = None,
) -> TraceRun:
    return TraceRun.model_validate(
        {
            "run_id": "run_test",
            "scenario_id": scenario_id,
            "trial": 1,
            "input": "hello",
            "started_at": "2026-05-01T00:00:00Z",
            "ended_at": "2026-05-01T00:00:01Z",
            "status": "completed",
            "steps": steps or [],
            "final_output": final_output,
        }
    )
