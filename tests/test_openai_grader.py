from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from openai.lib._parsing._completions import type_to_response_format_param

from anvil.grading import OpenAISemanticGrade, OpenAISemanticGrader, OpenAISuggestedFix
from anvil.scenario import ExpectedBehavior, ScenarioCase
from anvil.trace import TraceRun


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object):
        self.calls.append(kwargs)

        class ParsedResponse:
            output_parsed = OpenAISemanticGrade(
                passed=False,
                score=0.42,
                failure_type="premature_tool_execution",
                severity="high",
                reason="The agent issued a refund too early.",
                suggested_fix=OpenAISuggestedFix(
                    prompt_patch="Require verification first.",
                    tool_description_patch="Only call issue_refund after lookup_order.",
                    guardrail_patch="Block issue_refund until verified.",
                ),
            )

        return ParsedResponse()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_semantic_grader_uses_responses_parse_with_semantic_schema() -> None:
    client = FakeClient()
    grader = OpenAISemanticGrader(client=client, model="gpt-5.5")
    scenario = ScenarioCase(
        id="refund_missing_order_id",
        input="I want a refund, but I don't know my order number.",
        expected=ExpectedBehavior(
            should_not_call_tools=["issue_refund"],
            success_criteria=["Does not invent an order ID"],
        ),
    )
    trace = TraceRun(
        run_id="run_test",
        scenario_id=scenario.id,
        trial=1,
        input=scenario.input,
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 1, tzinfo=UTC),
        status="completed",
        steps=[
            {
                "type": "tool_call",
                "tool_name": "issue_refund",
                "arguments": {"order_id": "UNKNOWN"},
                "result": {"status": "refunded"},
            }
        ],
        final_output="Refund issued.",
    )

    grade = grader.grade(scenario, trace)

    assert grade.failure_type == "premature_tool_execution"
    assert grade.suggested_fix["guardrail_patch"] == "Block issue_refund until verified."
    assert client.responses.calls[0]["model"] == "gpt-5.5"
    assert client.responses.calls[0]["text_format"] is OpenAISemanticGrade
    input_messages = cast(list[dict[str, str]], client.responses.calls[0]["input"])
    system_prompt = input_messages[0]["content"]
    assert "For failing traces, fill every suggested_fix field" in system_prompt


def test_openai_semantic_grader_redacts_sensitive_payload_by_default() -> None:
    client = FakeClient()
    grader = OpenAISemanticGrader(client=client, model="gpt-5.4-mini")
    scenario = ScenarioCase(
        id="refund_email_lookup",
        input="Refund order ORD-123 for alice@example.com. My phone is +1 415-555-2671.",
        expected=ExpectedBehavior(
            should_call_tools=["lookup_customer"],
            success_criteria=["Uses customer lookup before refund."],
        ),
    )
    trace = TraceRun(
        run_id="run_test",
        scenario_id=scenario.id,
        trial=1,
        input=scenario.input,
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 1, tzinfo=UTC),
        status="completed",
        steps=[
            {
                "type": "model_call",
                "model": "gpt-5.4-mini",
                "input": (
                    "Authorization: Bearer live-token-1234567890 "
                    "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
                    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c "
                    "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz "
                    "secret=supersecretvalue123"
                ),
                "output_text": "",
                "tool_calls": [],
            },
            {
                "type": "tool_call",
                "tool_name": "lookup_customer",
                "arguments": {
                    "email_or_phone": "alice@example.com",
                    "customer_id": "CUS-777",
                    "api_key": "plain-api-key-value",
                    "password": "plain-password-value",
                    "access_token": "plain-access-token-value",
                },
                "result": {
                    "order_id": "ORD-123",
                    "phone": "+1 415-555-2671",
                    "customer_id": "cus_123",
                    "client_secret": "plain-client-secret-value",
                },
            },
        ],
        final_output="I found order ORD-123 for alice@example.com.",
    )

    grader.grade(scenario, trace)

    input_messages = cast(list[dict[str, str]], client.responses.calls[0]["input"])
    payload = input_messages[1]["content"]
    assert "alice@example.com" not in payload
    assert "ORD-123" not in payload
    assert "CUS-777" not in payload
    assert "cus_123" not in payload
    assert "415-555-2671" not in payload
    assert "live-token-1234567890" not in payload
    assert "eyJhbGciOiJIUzI1NiJ9" not in payload
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz" not in payload
    assert "supersecretvalue123" not in payload
    assert "plain-api-key-value" not in payload
    assert "plain-password-value" not in payload
    assert "plain-access-token-value" not in payload
    assert "plain-client-secret-value" not in payload
    assert "[REDACTED_EMAIL]" in payload
    assert "[REDACTED_ORDER_ID]" in payload
    assert "[REDACTED_CUSTOMER_ID]" in payload
    assert "[REDACTED_PHONE]" in payload
    assert "[REDACTED_BEARER_TOKEN]" in payload
    assert "[REDACTED_JWT]" in payload
    assert "[REDACTED_API_KEY]" in payload
    assert "[REDACTED_SECRET]" in payload


def test_openai_semantic_grader_applies_custom_redaction_patterns() -> None:
    client = FakeClient()
    grader = OpenAISemanticGrader(
        client=client,
        model="gpt-5.4-mini",
        redaction_patterns=[r"tenant-[0-9]{4}"],
    )
    scenario = ScenarioCase(
        id="tenant_debug",
        input="Debug tenant-1234.",
        expected=ExpectedBehavior(success_criteria=["Keep tenant private."]),
    )
    trace = TraceRun(
        run_id="run_test",
        scenario_id=scenario.id,
        trial=1,
        input=scenario.input,
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 1, tzinfo=UTC),
        status="completed",
        steps=[],
        final_output="tenant-1234 was checked.",
    )

    grader.grade(scenario, trace)

    input_messages = cast(list[dict[str, str]], client.responses.calls[0]["input"])
    payload = input_messages[1]["content"]
    assert "tenant-1234" not in payload
    assert "[REDACTED_CUSTOM]" in payload


def test_openai_semantic_grader_can_disable_redaction_for_debugging() -> None:
    client = FakeClient()
    grader = OpenAISemanticGrader(client=client, model="gpt-5.4-mini", redact=False)
    scenario = ScenarioCase(
        id="refund_email_lookup",
        input="Refund order ORD-123 for alice@example.com.",
        expected=ExpectedBehavior(success_criteria=["Debug exact payload."]),
    )
    trace = TraceRun(
        run_id="run_test",
        scenario_id=scenario.id,
        trial=1,
        input=scenario.input,
        started_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 20, 0, 1, tzinfo=UTC),
        status="completed",
        steps=[],
        final_output="Refund order ORD-123 for alice@example.com.",
    )

    grader.grade(scenario, trace)

    input_messages = cast(list[dict[str, str]], client.responses.calls[0]["input"])
    payload = input_messages[1]["content"]
    assert "alice@example.com" in payload
    assert "ORD-123" in payload


def test_openai_semantic_grade_schema_uses_fixed_suggested_fix_fields() -> None:
    response_format = type_to_response_format_param(OpenAISemanticGrade)
    response_format_dict = cast(dict[str, Any], response_format)
    schema = response_format_dict["json_schema"]["schema"]

    assert "suggested_fix" in schema["properties"]
    assert "suggested_fix" in schema["required"]
    suggested_fix_ref = schema["properties"]["suggested_fix"]["$ref"]
    suggested_fix_schema = schema["$defs"][suggested_fix_ref.removeprefix("#/$defs/")]
    assert set(suggested_fix_schema["properties"]) == {
        "prompt_patch",
        "tool_description_patch",
        "guardrail_patch",
    }
    assert suggested_fix_schema["additionalProperties"] is False
