from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from anvil.cli import app
from anvil.doctor import DoctorReportPayload
from anvil.leaderboard import (
    LeaderboardAuditReport,
    LeaderboardEvidenceVerificationIndex,
    LeaderboardGithubRunVerification,
    LeaderboardIndex,
    LeaderboardMaintainerRerun,
    LeaderboardSubmission,
)
from anvil.runner import CompareResultPayload
from anvil.scenario import ScenarioSuite
from anvil.storage import ResultsPayload, RunManifestPayload
from anvil.trace import TraceRun

CONTRACT_SCHEMAS = {
    "anvil.trace.v1": "anvil.trace.v1.schema.json",
    "anvil.scenario.v1": "anvil.scenario.v1.schema.json",
    "anvil.results.v1": "anvil.results.v1.schema.json",
    "anvil.run_manifest.v1": "anvil.run_manifest.v1.schema.json",
    "anvil.doctor.report.v1": "anvil.doctor.report.v1.schema.json",
    "anvil.compare.result.v1": "anvil.compare.result.v1.schema.json",
    "agent-anvil.leaderboard.v1": "agent-anvil.leaderboard.v1.schema.json",
    "agent-anvil.leaderboard.index.v1": "agent-anvil.leaderboard.index.v1.schema.json",
    "agent-anvil.leaderboard.github_run_verification.v1": (
        "agent-anvil.leaderboard.github_run_verification.v1.schema.json"
    ),
    "agent-anvil.leaderboard.audit.v1": "agent-anvil.leaderboard.audit.v1.schema.json",
    "agent-anvil.leaderboard.evidence_index.v1": (
        "agent-anvil.leaderboard.evidence_index.v1.schema.json"
    ),
    "agent-anvil.leaderboard.maintainer_rerun.v1": (
        "agent-anvil.leaderboard.maintainer_rerun.v1.schema.json"
    ),
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


def test_cli_schema_validate_accepts_auto_detected_json_contract() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "schema",
            "validate",
            "fixtures/contracts/leaderboard-evidence-index-valid.json",
        ],
    )

    assert result.exit_code == 0
    assert "Schema: agent-anvil.leaderboard.evidence_index.v1" in result.stdout
    assert "Contract is valid" in result.stdout


def test_cli_schema_validate_accepts_explicit_yaml_contract() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "schema",
            "validate",
            "fixtures/contracts/scenario-valid.yaml",
            "--schema",
            "anvil.scenario.v1",
        ],
    )

    assert result.exit_code == 0
    assert "Schema: anvil.scenario.v1" in result.stdout
    assert "Contract is valid" in result.stdout


def test_cli_schema_validate_rejects_invalid_contract(tmp_path: Path) -> None:
    invalid_path = tmp_path / "bad-evidence-index.json"
    invalid_path.write_text(
        '{"schema_version": "agent-anvil.leaderboard.evidence_index.v1"}',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["schema", "validate", str(invalid_path)])

    assert result.exit_code == 1
    assert "invalid agent-anvil.leaderboard.evidence_index.v1 contract" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_schema_validate_dir_accepts_auto_detected_json_contracts(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "submission.json").write_text(
        Path("fixtures/contracts/leaderboard-submission-valid.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (contracts_dir / "evidence-index.json").write_text(
        Path("fixtures/contracts/leaderboard-evidence-index-valid.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["schema", "validate-dir", str(contracts_dir)])

    assert result.exit_code == 0
    assert "Valid contracts: 2" in result.stdout
    assert "submission.json: agent-anvil.leaderboard.v1" in result.stdout
    assert "evidence-index.json: agent-anvil.leaderboard.evidence_index.v1" in result.stdout


def test_cli_schema_validate_dir_rejects_invalid_contracts(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "submission.json").write_text(
        Path("fixtures/contracts/leaderboard-submission-valid.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (contracts_dir / "broken.json").write_text(
        '{"schema_version": "agent-anvil.leaderboard.v1"}',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["schema", "validate-dir", str(contracts_dir)])

    assert result.exit_code == 1
    assert "Valid contracts: 1" in result.stdout
    assert "Invalid contracts: 1" in result.stderr
    assert "broken.json: invalid agent-anvil.leaderboard.v1 contract" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_schema_validate_dir_recurses_when_requested(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "contracts"
    nested_dir = contracts_dir / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "submission.json").write_text(
        Path("fixtures/contracts/leaderboard-submission-valid.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["schema", "validate-dir", str(contracts_dir), "--recursive"])

    assert result.exit_code == 0
    assert "Valid contracts: 1" in result.stdout
    assert "nested/submission.json: agent-anvil.leaderboard.v1" in result.stdout


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
    verification = LeaderboardGithubRunVerification.model_validate_json(
        Path("fixtures/contracts/leaderboard-github-run-verification-valid.json").read_text(
            encoding="utf-8"
        )
    )
    audit = LeaderboardAuditReport.model_validate_json(
        Path("fixtures/contracts/leaderboard-audit-valid.json").read_text(encoding="utf-8")
    )
    evidence_index = LeaderboardEvidenceVerificationIndex.model_validate_json(
        Path("fixtures/contracts/leaderboard-evidence-index-valid.json").read_text(encoding="utf-8")
    )
    maintainer_rerun = LeaderboardMaintainerRerun.model_validate_json(
        Path("fixtures/contracts/leaderboard-maintainer-rerun-valid.json").read_text(
            encoding="utf-8"
        )
    )
    doctor = DoctorReportPayload.model_validate_json(
        Path("fixtures/contracts/doctor-report-valid.json").read_text(encoding="utf-8")
    )
    results = ResultsPayload.model_validate_json(
        Path("fixtures/contracts/results-valid.json").read_text(encoding="utf-8")
    )
    run_manifest = RunManifestPayload.model_validate_json(
        Path("fixtures/contracts/run-manifest-valid.json").read_text(encoding="utf-8")
    )
    compare = CompareResultPayload.model_validate_json(
        Path("fixtures/contracts/compare-result-valid.json").read_text(encoding="utf-8")
    )

    assert valid_trace.schema_version == "anvil.trace.v1"
    assert failed_trace.status == "failed"
    assert failed_trace.steps[0].get("type") == "agent_protocol_error"
    assert scenario.name == "contract_scenario_suite"
    assert results.schema_version == "anvil.results.v1"
    assert results.summary.pass_rate == 100.0
    assert run_manifest.schema_version == "anvil.run_manifest.v1"
    assert run_manifest.files[0].path == "report.md"
    assert doctor.schema_version == "anvil.doctor.report.v1"
    assert doctor.checks[0].name == "scenario_file"
    assert compare.schema_version == "anvil.compare.result.v1"
    assert compare.new_failures[0].failure_type == "invalid_tool_args"
    assert submission.schema_version == "agent-anvil.leaderboard.v1"
    assert index.schema_version == "agent-anvil.leaderboard.index.v1"
    assert verification.schema_version == "agent-anvil.leaderboard.github_run_verification.v1"
    assert verification.status == "verified"
    assert audit.schema_version == "agent-anvil.leaderboard.audit.v1"
    assert audit.summary.review == 1
    assert evidence_index.schema_version == "agent-anvil.leaderboard.evidence_index.v1"
    assert evidence_index.summary.maintainer_rerun == 1
    assert maintainer_rerun.schema_version == "agent-anvil.leaderboard.maintainer_rerun.v1"
    assert maintainer_rerun.status == "verified"


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
    assert "schemas/anvil.results.v1.schema.json" in artifacts
    assert "schemas/anvil.run_manifest.v1.schema.json" in artifacts
    assert "schemas/anvil.compare.result.v1.schema.json" in artifacts
    assert "schemas/agent-anvil.leaderboard.github_run_verification.v1.schema.json" in artifacts
    assert "schemas/agent-anvil.leaderboard.audit.v1.schema.json" in artifacts
    assert "schemas/agent-anvil.leaderboard.maintainer_rerun.v1.schema.json" in contracts

    assert "uv run anvil schema export --out schemas" in contracts
    assert "uv run anvil schema export --out schemas" in cli_doc
    assert "artifact trust summary" in cli_doc
    assert "fixtures/contracts/trace-valid.json" in contracts
    assert "fixtures/contracts/results-valid.json" in contracts
    assert "fixtures/contracts/run-manifest-valid.json" in contracts
    assert "fixtures/contracts/doctor-report-valid.json" in contracts
    assert "fixtures/contracts/compare-result-valid.json" in contracts
    assert "fixtures/contracts/leaderboard-github-run-verification-valid.json" in contracts
    assert "fixtures/contracts/leaderboard-audit-valid.json" in contracts
    assert "fixtures/contracts/leaderboard-evidence-index-valid.json" in contracts
    assert "fixtures/contracts/leaderboard-maintainer-rerun-valid.json" in contracts
    assert "External Agent Conformance" in contracts
    assert "compatible HTTP endpoint agent" in contracts
    assert "anvil.schema.export.v1" in contracts
    assert "contracts.md" in schema_versioning
