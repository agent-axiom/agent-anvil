from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from anvil.scenario import ScenarioSuite, load_scenario_file


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
