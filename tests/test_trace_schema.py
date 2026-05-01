from __future__ import annotations

from datetime import UTC, datetime

from anvil.trace import TraceRun


def test_trace_run_round_trips_to_json(trace_steps: list[dict[str, object]]) -> None:
    trace = TraceRun(
        run_id="run_20260501_001",
        scenario_id="refund_valid_order",
        trial=1,
        input="Please refund order ORD-123. It arrived broken.",
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 4, tzinfo=UTC),
        status="completed",
        steps=trace_steps,
        final_output="Refund issued for ORD-123.",
    )

    restored = TraceRun.model_validate_json(trace.model_dump_json())

    assert restored.metrics.latency_ms == 4000
    assert restored.metrics.tool_call_count == 2
    assert restored.metrics.model_call_count == 1
    assert restored.tool_names() == ["lookup_order", "issue_refund"]


def test_trace_run_counts_missing_end_as_zero_latency(
    trace_steps: list[dict[str, object]],
) -> None:
    trace = TraceRun(
        run_id="run_20260501_001",
        scenario_id="refund_valid_order",
        trial=1,
        input="Please refund order ORD-123. It arrived broken.",
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=None,
        status="running",
        steps=trace_steps,
        final_output=None,
    )

    assert trace.metrics.latency_ms == 0
    assert trace.metrics.tool_call_count == 2
