from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from anvil.scenario import ExternalAgentConfig, ScenarioSuite, load_scenario_file


def test_load_scenario_file_preserves_suite_defaults(scenario_file: Path) -> None:
    suite = load_scenario_file(scenario_file)

    assert suite.name == "refund_agent_regression_suite"
    assert suite.agent == "examples.support_agent"
    assert suite.defaults.trials == 3
    assert suite.defaults.max_steps == 8
    assert [scenario.id for scenario in suite.scenarios] == [
        "refund_missing_order_id",
        "refund_valid_order",
    ]


def test_load_scenario_file_parses_expected_tool_contracts(scenario_file: Path) -> None:
    suite = load_scenario_file(scenario_file)
    valid_order = suite.scenarios[1]

    assert valid_order.expected.should_call_tools == ["lookup_order", "issue_refund"]
    assert valid_order.expected.required_tool_args == {"issue_refund": {"order_id": "ORD-123"}}
    assert valid_order.trials(suite.defaults) == 3
    assert valid_order.max_steps(suite.defaults) == 8


def test_refund_missing_order_without_identity_does_not_require_customer_lookup(
    scenario_file: Path,
) -> None:
    suite = load_scenario_file(scenario_file)
    missing_order = suite.scenarios[0]

    assert missing_order.id == "refund_missing_order_id"
    assert missing_order.expected.should_call_tools == []
    assert missing_order.expected.should_not_call_tools == ["issue_refund"]
    assert missing_order.expected.should_ask_clarifying_question is True


def test_load_scenario_file_accepts_external_agent_config(tmp_path: Path) -> None:
    scenario_file = tmp_path / "external.yaml"
    scenario_file.write_text(
        """
name: external_agent_suite
agent:
  command: "python my_agent.py"
  protocol: jsonl
  cwd: agents/support
  env:
    AGENT_MODE: test
scenarios:
  - id: smoke
    input: "hello"
""",
        encoding="utf-8",
    )

    suite = load_scenario_file(scenario_file)

    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.command == "python my_agent.py"
    assert suite.agent.protocol == "jsonl"
    assert suite.agent.cwd == "agents/support"
    assert suite.agent.env == {"AGENT_MODE": "test"}


def test_load_scenario_file_accepts_http_agent_config(tmp_path: Path) -> None:
    scenario_file = tmp_path / "http-agent.yaml"
    scenario_file.write_text(
        """
name: http_agent_suite
agent:
  protocol: http
  url: "http://127.0.0.1:8080/anvil"
  timeout_seconds: 3
  headers:
    X-Agent-Anvil: test
scenarios:
  - id: smoke
    input: "hello"
""",
        encoding="utf-8",
    )

    suite = load_scenario_file(scenario_file)

    assert isinstance(suite.agent, ExternalAgentConfig)
    assert suite.agent.protocol == "http"
    assert suite.agent.url == "http://127.0.0.1:8080/anvil"
    assert suite.agent.timeout_seconds == 3
    assert suite.agent.headers == {"X-Agent-Anvil": "test"}


def test_load_scenario_file_accepts_tool_safety_policies(tmp_path: Path) -> None:
    scenario_file = tmp_path / "policy.yaml"
    scenario_file.write_text(
        """
name: policy_suite
agent: examples.support_agent
policies:
  destructive_tools:
    - issue_refund
  require_before:
    issue_refund:
      - tool: lookup_order
        result:
          eligible_for_refund: true
  require_human_approval:
    - delete_project
scenarios:
  - id: smoke
    input: "refund ORD-123"
""",
        encoding="utf-8",
    )

    suite = load_scenario_file(scenario_file)

    assert suite.policies.destructive_tools == ["issue_refund"]
    assert suite.policies.require_before["issue_refund"][0].tool == "lookup_order"
    assert suite.policies.require_before["issue_refund"][0].result == {"eligible_for_refund": True}
    assert suite.policies.require_human_approval == ["delete_project"]


def test_load_scenario_file_accepts_assertion_dsl(tmp_path: Path) -> None:
    scenario_file = tmp_path / "assertions.yaml"
    scenario_file.write_text(
        """
name: assertion_suite
agent: examples.support_agent
scenarios:
  - id: refund_order
    input: "Refund ORD-123"
    expected:
      assertions:
        - type: tool_called
          tool: lookup_order
        - type: tool_called_before
          before: issue_refund
          after: lookup_order
        - type: max_tool_calls
          tool: lookup_order
          count: 1
        - type: forbidden_arg_value
          tool: issue_refund
          path: $.order_id
          values: ["UNKNOWN", "", null]
        - type: tool_result_matches
          tool: lookup_order
          path: $.eligible_for_refund
          equals: true
        - type: final_output_not_contains
          text: "guaranteed"
""",
        encoding="utf-8",
    )

    suite = load_scenario_file(scenario_file)
    assertions = suite.scenarios[0].expected.assertions

    assert [assertion.type for assertion in assertions] == [
        "tool_called",
        "tool_called_before",
        "max_tool_calls",
        "forbidden_arg_value",
        "tool_result_matches",
        "final_output_not_contains",
    ]
    assert assertions[3].values == ["UNKNOWN", "", None]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "name"),
        ({"name": "suite", "agent": "examples.support_agent", "scenarios": []}, "scenarios"),
        (
            {
                "name": "suite",
                "agent": "examples.support_agent",
                "scenarios": [{"id": "missing_input", "expected": {}}],
            },
            "input",
        ),
    ],
)
def test_scenario_suite_rejects_invalid_payloads(payload: dict[str, object], field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioSuite.model_validate(payload)

    assert field in str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {
                "name": "suite",
                "agent": "examples.support_agent",
                "unknown_suite_field": True,
                "scenarios": [{"id": "smoke", "input": "hello"}],
            },
            "unknown_suite_field",
        ),
        (
            {
                "name": "suite",
                "agent": {"command": "python agent.py", "protocol": "jsonl", "shell": True},
                "scenarios": [{"id": "smoke", "input": "hello"}],
            },
            "shell",
        ),
        (
            {
                "name": "suite",
                "agent": "examples.support_agent",
                "defaults": {"trials": 1, "retry_count": 3},
                "scenarios": [{"id": "smoke", "input": "hello"}],
            },
            "retry_count",
        ),
        (
            {
                "name": "suite",
                "agent": "examples.support_agent",
                "scenarios": [
                    {
                        "id": "smoke",
                        "input": "hello",
                        "expected": {"should_never_call_tools": ["delete_project"]},
                    }
                ],
            },
            "should_never_call_tools",
        ),
        (
            {
                "name": "suite",
                "agent": "examples.support_agent",
                "scenarios": [{"id": "smoke", "input": "hello", "timeout": 10}],
            },
            "timeout",
        ),
        (
            {
                "name": "suite",
                "agent": "examples.support_agent",
                "scenarios": [
                    {
                        "id": "smoke",
                        "input": "hello",
                        "expected": {"assertions": [{"type": "tool_called"}]},
                    }
                ],
            },
            "tool",
        ),
    ],
)
def test_scenario_suite_rejects_unknown_fields(
    payload: dict[str, object],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioSuite.model_validate(payload)

    assert field in str(exc_info.value)
