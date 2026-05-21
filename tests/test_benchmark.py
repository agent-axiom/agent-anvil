from __future__ import annotations

import pytest
from pydantic import ValidationError

from anvil.benchmark import BenchmarkManifest, FinalAnswerBaseline, load_benchmark_manifest
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
