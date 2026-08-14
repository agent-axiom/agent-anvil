from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from anvil.assurance.contracts import ReleaseContract
from anvil.assurance.evidence import EvidenceRecord, verify_evidence_identity
from anvil.attestations import LeaderboardArtifactAttestationVerification
from anvil.cli import app
from anvil.contracts import (
    ContractValidationError,
    validate_schema_contract,
)
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
    "assurance.anvil.dev/release-contract/v1alpha1": (
        "assurance.anvil.dev.release-contract.v1alpha1.schema.json"
    ),
    "assurance.anvil.dev/evidence-record/v1alpha1": (
        "assurance.anvil.dev.evidence-record.v1alpha1.schema.json"
    ),
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
    "agent-anvil.leaderboard.artifact_attestation_verification.v1": (
        "agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json"
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


def test_schema_validate_preserves_legacy_scenario_yaml_alias_support(tmp_path: Path) -> None:
    scenario = Path("fixtures/contracts/scenario-valid.yaml").read_text(encoding="utf-8")
    scenario = scenario.replace(
        "trials: 1\n  max_steps: 6", "trials: &count 1\n  max_steps: *count"
    )
    path = tmp_path / "scenario.yaml"
    path.write_text(scenario, encoding="utf-8")

    assert validate_schema_contract(path, schema_id="anvil.scenario.v1") == "anvil.scenario.v1"


def test_cli_schema_validate_accepts_explicit_assurance_yaml_contract() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "schema",
            "validate",
            "fixtures/contracts/assurance-release-contract-valid.yaml",
            "--schema",
            "assurance.anvil.dev/release-contract/v1alpha1",
        ],
    )

    assert result.exit_code == 0
    assert "Schema: assurance.anvil.dev/release-contract/v1alpha1" in result.stdout
    assert "Contract is valid" in result.stdout


def test_cli_schema_validate_rejects_duplicate_assurance_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(
        "kind: AttackerSelected\n"
        + Path("fixtures/contracts/assurance-release-contract-valid.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "schema",
            "validate",
            str(path),
            "--schema",
            "assurance.anvil.dev/release-contract/v1alpha1",
        ],
    )

    assert result.exit_code == 1
    assert "duplicate YAML key" in result.stderr
    assert "Traceback" not in result.stderr


def test_schema_validate_normalizes_malformed_assurance_yaml(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("metadata: [unterminated\n", encoding="utf-8")

    with pytest.raises(ContractValidationError, match="invalid YAML contract") as captured:
        validate_schema_contract(
            path,
            schema_id="assurance.anvil.dev/release-contract/v1alpha1",
        )

    assert captured.value.__cause__ is None


def test_cli_schema_validate_auto_detects_assurance_evidence_contract() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "schema",
            "validate",
            "fixtures/contracts/assurance-evidence-record-valid.json",
        ],
    )

    assert result.exit_code == 0
    assert "Schema: assurance.anvil.dev/evidence-record/v1alpha1" in result.stdout
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


def test_schema_validate_rejects_oversized_json_during_auto_detection(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_bytes(b'"' + b"x" * (1024 * 1024) + b'"')

    with pytest.raises(ContractValidationError, match="maximum encoded size"):
        validate_schema_contract(path)


def test_schema_validate_accepts_large_legacy_trace_with_explicit_schema(tmp_path: Path) -> None:
    payload = json.loads(Path("fixtures/contracts/trace-valid.json").read_text(encoding="utf-8"))
    payload["final_output"] = "x" * (1024 * 1024)
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert validate_schema_contract(path, schema_id="anvil.trace.v1") == "anvil.trace.v1"


def test_schema_validate_opens_json_contract_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "trace.json"
    path.write_text(
        Path("fixtures/contracts/trace-valid.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    real_open = os.open
    observed_flags: list[int] = []

    def recording_open(
        selected_path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed_flags.append(flags)
        if dir_fd is None:
            return real_open(selected_path, flags, mode)
        return real_open(selected_path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", recording_open)

    assert validate_schema_contract(path, schema_id="anvil.trace.v1") == "anvil.trace.v1"
    assert observed_flags
    assert observed_flags[0] & os.O_NONBLOCK


def test_schema_validate_rejects_non_regular_json_input(tmp_path: Path) -> None:
    with pytest.raises(ContractValidationError, match="regular file"):
        validate_schema_contract(tmp_path, schema_id="anvil.trace.v1")


def test_schema_validate_normalizes_deep_json_parser_failure(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_text("[" * 2_000 + "]" * 2_000, encoding="utf-8")

    with pytest.raises(ContractValidationError, match="nesting is too deep") as captured:
        validate_schema_contract(path, schema_id="anvil.trace.v1")

    assert captured.value.__cause__ is None


def test_schema_validate_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    source = Path("fixtures/contracts/assurance-evidence-record-valid.json").read_text(
        encoding="utf-8"
    )
    path = tmp_path / "evidence.json"
    path.write_text(
        source.replace(
            '"trustLevel": "L2"',
            '"trustLevel": "L3",\n  "trustLevel": "L2"',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractValidationError, match="duplicate JSON key") as captured:
        validate_schema_contract(path)

    assert captured.value.__cause__ is None


def test_schema_validate_normalizes_oversized_integer_failure(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_text('{"schema_version":"anvil.trace.v1","value":' + "9" * 5_000 + "}")

    with pytest.raises(ContractValidationError, match="invalid JSON contract") as captured:
        validate_schema_contract(path, schema_id="anvil.trace.v1")

    assert captured.value.__cause__ is None


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_schema_validate_rejects_nonfinite_json_numbers(tmp_path: Path, constant: str) -> None:
    source = Path("fixtures/contracts/trace-valid.json").read_text(encoding="utf-8")
    path = tmp_path / "trace.json"
    path.write_text(
        source.replace('"estimated_cost_usd": 0.0', f'"estimated_cost_usd": {constant}')
    )

    with pytest.raises(ContractValidationError, match="non-finite JSON number") as captured:
        validate_schema_contract(path, schema_id="anvil.trace.v1")

    assert captured.value.__cause__ is None


def test_schema_validate_does_not_echo_invalid_values_or_chain_validation_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "anvil.trace.v1",
                "run_id": "sk-must-not-leak",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractValidationError) as captured:
        validate_schema_contract(path)

    assert "sk-must-not-leak" not in str(captured.value)
    assert captured.value.__cause__ is None


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
    assurance_contract = ReleaseContract.model_validate(
        yaml.safe_load(
            Path("fixtures/contracts/assurance-release-contract-valid.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    assurance_evidence = EvidenceRecord.model_validate_json(
        Path("fixtures/contracts/assurance-evidence-record-valid.json").read_text(encoding="utf-8")
    )
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
    artifact_attestation = LeaderboardArtifactAttestationVerification.model_validate_json(
        Path(
            "fixtures/contracts/leaderboard-artifact-attestation-verification-valid.json"
        ).read_text(encoding="utf-8")
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
    assert assurance_contract.api_version == "assurance.anvil.dev/release-contract/v1alpha1"
    assert assurance_contract.release_id.startswith("sha256:")
    assert assurance_evidence.schema_version == "assurance.anvil.dev/evidence-record/v1alpha1"
    assert assurance_evidence.release_id == assurance_contract.release_id
    assert verify_evidence_identity(assurance_evidence) is None
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
    assert artifact_attestation.schema_version == (
        "agent-anvil.leaderboard.artifact_attestation_verification.v1"
    )
    assert artifact_attestation.subject_sha256 == "1" * 64
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
    assert (
        "schemas/agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json"
        in artifacts
    )
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
    assert (
        "fixtures/contracts/leaderboard-artifact-attestation-verification-valid.json" in contracts
    )
    assert "fixtures/contracts/leaderboard-audit-valid.json" in contracts
    assert "fixtures/contracts/leaderboard-evidence-index-valid.json" in contracts
    assert "fixtures/contracts/leaderboard-maintainer-rerun-valid.json" in contracts
    assert "External Agent Conformance" in contracts
    assert "compatible HTTP endpoint agent" in contracts
    assert "anvil.schema.export.v1" in contracts
    assert "contracts.md" in schema_versioning


def test_assurance_schema_exports_use_public_wire_aliases(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["schema", "export", "--out", str(tmp_path)])

    assert result.exit_code == 0
    release_schema = json.loads(
        (tmp_path / "assurance.anvil.dev.release-contract.v1alpha1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    evidence_schema = json.loads(
        (tmp_path / "assurance.anvil.dev.evidence-record.v1alpha1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert "apiVersion" in release_schema["properties"]
    assert "api_version" not in release_schema["properties"]
    assert "schemaVersion" in evidence_schema["properties"]
    assert "schema_version" not in evidence_schema["properties"]


def test_assurance_contract_docs_define_trust_and_compatibility_boundaries() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    contracts = Path("docs/contracts.md").read_text(encoding="utf-8")
    schema_versioning = Path("docs/schema-versioning.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    trust = Path("docs/assurance-trust.md").read_text(encoding="utf-8")

    assert "docs/assurance-trust.md" in readme
    assert "Experimental Assurance foundation" in readme
    for filename in (
        "assurance-release-contract-valid.yaml",
        "assurance-evidence-record-valid.json",
        "assurance.anvil.dev.release-contract.v1alpha1.schema.json",
        "assurance.anvil.dev.evidence-record.v1alpha1.schema.json",
    ):
        assert filename in contracts
    assert "assurance.anvil.dev/release-contract/v1alpha1" in contracts
    assert "assurance.anvil.dev/evidence-record/v1alpha1" in contracts
    assert "duplicate YAML keys" in contracts
    assert "YAML aliases" in contracts
    assert "1 MiB" in contracts
    assert "canonical finite JSON values" in contracts
    assert "secret-like keys" in contracts
    assert "inspection-only" in contracts
    assert "CheckTypeRegistry" in contracts
    assert "v1alpha2" in schema_versioning
    assert "unknown fields are rejected" in schema_versioning
    assert "evidenceId" in artifacts
    assert "content.sha256" in artifacts
    assert "normalized relative" in artifacts
    assert "64 MiB" in artifacts
    assert "must not reopen" in artifacts
    assert "Trust describes observation provenance, not whether the agent is safe." in trust
    for level in ("L0", "L1", "L2", "L3"):
        assert level in trust
    for limitation in (
        "host root",
        "collector implementation",
        "trust root",
        "model provider",
        "environment integrity",
    ):
        assert limitation in trust
    assert "no Assurance runner" in trust
    assert "no verdict engine" in trust
    assert "ObservedEvidenceSource" in trust
    assert "trusted ingestion boundary" in trust
    assert "contractId" in trust
