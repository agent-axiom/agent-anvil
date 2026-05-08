from __future__ import annotations

from datetime import UTC, datetime

from anvil.trace import AgentProtocolErrorStep, ModelCallStep, ToolCallStep, TraceRun


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


def test_trace_steps_are_typed_but_dict_compatible(trace_steps: list[dict[str, object]]) -> None:
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

    assert isinstance(trace.steps[0], ModelCallStep)
    assert isinstance(trace.steps[1], ToolCallStep)
    assert trace.steps[1]["tool_name"] == "lookup_order"
    assert trace.steps[1].get("arguments") == {"order_id": "ORD-123"}

    payload = trace.model_dump(mode="json")
    assert payload["steps"][0]["type"] == "model_call"
    assert payload["steps"][1]["tool_name"] == "lookup_order"


def test_trace_supports_typed_protocol_error_step() -> None:
    trace = TraceRun(
        run_id="run_20260501_001",
        scenario_id="external_agent_timeout",
        trial=1,
        input="Check order ORD-123.",
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 4, tzinfo=UTC),
        status="failed",
        steps=[
            {
                "type": "agent_protocol_error",
                "error_type": "timeout",
                "message": "Agent command timed out.",
            }
        ],
        final_output="Agent command timed out.",
    )

    assert isinstance(trace.steps[0], AgentProtocolErrorStep)
    assert trace.steps[0]["error_type"] == "timeout"
