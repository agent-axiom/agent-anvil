from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from anvil.cli import app
from anvil.doctor import DoctorReportPayload
from anvil.leaderboard import LeaderboardIndex, LeaderboardSubmission
from anvil.scenario import ScenarioSuite
from anvil.trace import TraceRun

CONTRACT_SCHEMAS = {
    "anvil.trace.v1": "anvil.trace.v1.schema.json",
    "anvil.scenario.v1": "anvil.scenario.v1.schema.json",
    "anvil.doctor.report.v1": "anvil.doctor.report.v1.schema.json",
    "agent-anvil.leaderboard.v1": "agent-anvil.leaderboard.v1.schema.json",
    "agent-anvil.leaderboard.index.v1": "agent-anvil.leaderboard.index.v1.schema.json",
}


def test_cli_schema_export_writes_stable_contract_schemas(tmp_path: Path) -> None:
    out_dir = tmp_path / "schemas"
    runner = CliRunner()

    result = runner.invoke(app, ["schema", "export", "--out", str(out_dir)])

    assert result.exit_code == 0
    for schema_id, filename in CONTRACT_SCHEMAS.items():
        schema_path = out_dir / filename
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == schema_id
        assert schema["x-agent-anvil-schema-version"] == schema_id
        assert filename in result.stdout


def test_checked_in_schemas_match_exported_contracts(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["schema", "export", "--out", str(tmp_path)])

    assert result.exit_code == 0
    for filename in CONTRACT_SCHEMAS.values():
        checked_in = json.loads(Path("schemas", filename).read_text(encoding="utf-8"))
        exported = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert exported == checked_in


def test_golden_contract_fixtures_validate_against_pydantic_models() -> None:
    valid_trace = TraceRun.model_validate_json(
        Path("fixtures/contracts/trace-valid.json").read_text(encoding="utf-8")
    )
    failed_trace = TraceRun.model_validate_json(
        Path("fixtures/contracts/trace-protocol-error.json").read_text(encoding="utf-8")
    )
    scenario = ScenarioSuite.model_validate(
        yaml.safe_load(Path("fixtures/contracts/scenario-valid.yaml").read_text(encoding="utf-8"))
    )
    submission = LeaderboardSubmission.model_validate_json(
        Path("fixtures/contracts/leaderboard-submission-valid.json").read_text(encoding="utf-8")
    )
    index = LeaderboardIndex.model_validate_json(
        Path("fixtures/contracts/leaderboard-index-valid.json").read_text(encoding="utf-8")
    )
    doctor = DoctorReportPayload.model_validate_json(
        Path("fixtures/contracts/doctor-report-valid.json").read_text(encoding="utf-8")
    )

    assert valid_trace.schema_version == "anvil.trace.v1"
    assert failed_trace.status == "failed"
    assert failed_trace.steps[0].get("type") == "agent_protocol_error"
    assert scenario.name == "contract_scenario_suite"
    assert doctor.schema_version == "anvil.doctor.report.v1"
    assert doctor.checks[0].name == "scenario_file"
    assert submission.schema_version == "agent-anvil.leaderboard.v1"
    assert index.schema_version == "agent-anvil.leaderboard.index.v1"


def test_contract_docs_link_schema_export_and_conformance_fixtures() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    cli_doc = Path("docs/cli.md").read_text(encoding="utf-8")
    contracts = Path("docs/contracts.md").read_text(encoding="utf-8")
    schema_versioning = Path("docs/schema-versioning.md").read_text(encoding="utf-8")

    assert "docs/contracts.md" in readme
    assert "contracts.md" in artifacts
    for text in (readme, artifacts):
        assert "schemas/anvil.trace.v1.schema.json" in text

    assert "uv run anvil schema export --out schemas" in contracts
    assert "uv run anvil schema export --out schemas" in cli_doc
    assert "fixtures/contracts/trace-valid.json" in contracts
    assert "fixtures/contracts/doctor-report-valid.json" in contracts
    assert "External Agent Conformance" in contracts
    assert "compatible HTTP endpoint agent" in contracts
    assert "anvil.schema.export.v1" in contracts
    assert "contracts.md" in schema_versioning
