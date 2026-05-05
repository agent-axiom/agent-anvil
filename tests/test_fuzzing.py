from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.fuzzing import fuzz_scenario_file
from anvil.scenario import load_scenario_file


def test_fuzz_scenario_file_generates_valid_mutation_suite(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "refund_fuzzed.yaml"

    generated = fuzz_scenario_file(scenario_file, out_path=out, mutations=4, focus="tool_safety")

    assert generated == out
    suite = load_scenario_file(out)
    assert suite.name == "refund_agent_regression_suite_fuzzed"
    assert len(suite.scenarios) == 4
    assert len({scenario.id for scenario in suite.scenarios}) == 4
    assert any("urgent" in scenario.input.lower() for scenario in suite.scenarios)
    assert suite.scenarios[0].expected.should_not_call_tools


def test_cli_fuzz_writes_scenario_file(scenario_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "fuzzed.yaml"

    result = CliRunner().invoke(
        app,
        [
            "fuzz",
            str(scenario_file),
            "--mutations",
            "3",
            "--focus",
            "tool_safety",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote {out}" in result.stdout
    assert len(load_scenario_file(out).scenarios) == 3
