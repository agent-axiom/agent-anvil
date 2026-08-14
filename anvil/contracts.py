from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from anvil.assurance.contracts import RELEASE_CONTRACT_SCHEMA_VERSION, ReleaseContract
from anvil.assurance.evidence import EVIDENCE_RECORD_SCHEMA_VERSION, EvidenceRecord
from anvil.assurance.yaml import ContractYamlError, load_bounded_yaml
from anvil.attestations import (
    ARTIFACT_ATTESTATION_VERIFICATION_SCHEMA_VERSION,
    LeaderboardArtifactAttestationVerification,
)
from anvil.doctor import DOCTOR_REPORT_SCHEMA_VERSION, DoctorReportPayload
from anvil.leaderboard import (
    LEADERBOARD_AUDIT_SCHEMA_VERSION,
    LEADERBOARD_EVIDENCE_INDEX_SCHEMA_VERSION,
    LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION,
    LEADERBOARD_INDEX_SCHEMA_VERSION,
    LEADERBOARD_MAINTAINER_RERUN_SCHEMA_VERSION,
    LEADERBOARD_SCHEMA_VERSION,
    LeaderboardAuditReport,
    LeaderboardEvidenceVerificationIndex,
    LeaderboardGithubRunVerification,
    LeaderboardIndex,
    LeaderboardMaintainerRerun,
    LeaderboardSubmission,
)
from anvil.runner import COMPARE_RESULT_SCHEMA_VERSION, CompareResultPayload
from anvil.scenario import ScenarioSuite
from anvil.storage import (
    RESULTS_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    ResultsPayload,
    RunManifestPayload,
)
from anvil.trace import TRACE_SCHEMA_VERSION, TraceRun

SCENARIO_SCHEMA_VERSION = "anvil.scenario.v1"
SCHEMA_EXPORT_SCHEMA_VERSION = "anvil.schema.export.v1"
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class SchemaContract:
    schema_id: str
    filename: str
    model: type[BaseModel]
    description: str


@dataclass(frozen=True)
class SchemaValidationRecord:
    path: Path
    schema_id: str | None
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class SchemaDirectoryValidationResult:
    root: Path
    records: tuple[SchemaValidationRecord, ...]

    @property
    def valid(self) -> tuple[SchemaValidationRecord, ...]:
        return tuple(record for record in self.records if record.passed)

    @property
    def invalid(self) -> tuple[SchemaValidationRecord, ...]:
        return tuple(record for record in self.records if not record.passed)

    @property
    def passed(self) -> bool:
        return not self.invalid


SCHEMA_CONTRACTS: tuple[SchemaContract, ...] = (
    SchemaContract(
        schema_id=RELEASE_CONTRACT_SCHEMA_VERSION,
        filename="assurance.anvil.dev.release-contract.v1alpha1.schema.json",
        model=ReleaseContract,
        description="Agent Anvil Assurance release contract schema.",
    ),
    SchemaContract(
        schema_id=EVIDENCE_RECORD_SCHEMA_VERSION,
        filename="assurance.anvil.dev.evidence-record.v1alpha1.schema.json",
        model=EvidenceRecord,
        description="Agent Anvil Assurance evidence record schema.",
    ),
    SchemaContract(
        schema_id=TRACE_SCHEMA_VERSION,
        filename="anvil.trace.v1.schema.json",
        model=TraceRun,
        description="Agent Anvil trace artifact schema.",
    ),
    SchemaContract(
        schema_id=SCENARIO_SCHEMA_VERSION,
        filename="anvil.scenario.v1.schema.json",
        model=ScenarioSuite,
        description="Agent Anvil YAML scenario suite schema.",
    ),
    SchemaContract(
        schema_id=RESULTS_SCHEMA_VERSION,
        filename="anvil.results.v1.schema.json",
        model=ResultsPayload,
        description="Agent Anvil persisted run results schema.",
    ),
    SchemaContract(
        schema_id=RUN_MANIFEST_SCHEMA_VERSION,
        filename="anvil.run_manifest.v1.schema.json",
        model=RunManifestPayload,
        description="Agent Anvil run artifact integrity manifest schema.",
    ),
    SchemaContract(
        schema_id=DOCTOR_REPORT_SCHEMA_VERSION,
        filename="anvil.doctor.report.v1.schema.json",
        model=DoctorReportPayload,
        description="Agent Anvil doctor diagnostic report schema.",
    ),
    SchemaContract(
        schema_id=COMPARE_RESULT_SCHEMA_VERSION,
        filename="anvil.compare.result.v1.schema.json",
        model=CompareResultPayload,
        description="Agent Anvil compare result schema for CI and PR-comment integrations.",
    ),
    SchemaContract(
        schema_id=LEADERBOARD_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.v1.schema.json",
        model=LeaderboardSubmission,
        description="Agent Anvil public leaderboard submission schema.",
    ),
    SchemaContract(
        schema_id=LEADERBOARD_INDEX_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.index.v1.schema.json",
        model=LeaderboardIndex,
        description="Agent Anvil public leaderboard index schema.",
    ),
    SchemaContract(
        schema_id=LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.github_run_verification.v1.schema.json",
        model=LeaderboardGithubRunVerification,
        description="Agent Anvil GitHub Actions run verification report schema.",
    ),
    SchemaContract(
        schema_id=ARTIFACT_ATTESTATION_VERIFICATION_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json",
        model=LeaderboardArtifactAttestationVerification,
        description="Agent Anvil GitHub artifact attestation verification report schema.",
    ),
    SchemaContract(
        schema_id=LEADERBOARD_AUDIT_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.audit.v1.schema.json",
        model=LeaderboardAuditReport,
        description="Agent Anvil public leaderboard maintainer audit report schema.",
    ),
    SchemaContract(
        schema_id=LEADERBOARD_EVIDENCE_INDEX_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.evidence_index.v1.schema.json",
        model=LeaderboardEvidenceVerificationIndex,
        description="Agent Anvil public leaderboard evidence verification index schema.",
    ),
    SchemaContract(
        schema_id=LEADERBOARD_MAINTAINER_RERUN_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.maintainer_rerun.v1.schema.json",
        model=LeaderboardMaintainerRerun,
        description="Agent Anvil public leaderboard maintainer rerun attestation schema.",
    ),
)
SCHEMA_CONTRACTS_BY_ID = {contract.schema_id: contract for contract in SCHEMA_CONTRACTS}


class ContractValidationError(ValueError):
    """Raised when an artifact does not match a stable Agent Anvil contract."""


def contract_schema(contract: SchemaContract) -> dict[str, Any]:
    schema = contract.model.model_json_schema(mode="validation", by_alias=True)
    schema["$schema"] = JSON_SCHEMA_DRAFT
    schema["$id"] = contract.schema_id
    schema["description"] = contract.description
    schema["x-agent-anvil-schema-version"] = contract.schema_id
    schema["x-agent-anvil-schema-export-version"] = SCHEMA_EXPORT_SCHEMA_VERSION
    return schema


def export_schema_contracts(out_dir: str | Path) -> list[Path]:
    selected_out_dir = Path(out_dir)
    selected_out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for contract in SCHEMA_CONTRACTS:
        path = selected_out_dir / contract.filename
        path.write_text(
            json.dumps(contract_schema(contract), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def validate_schema_contract(path: str | Path, schema_id: str | None = None) -> str:
    selected_path = Path(path)
    if schema_id is None:
        payload = _read_json_payload(selected_path)
        if not isinstance(payload, dict):
            raise ContractValidationError(
                f"schema_version auto-detection requires a JSON object at {selected_path}"
            )
        detected_schema_id = (
            payload.get("schema_version")
            or payload.get("schemaVersion")
            or payload.get("apiVersion")
        )
        if not isinstance(detected_schema_id, str) or not detected_schema_id:
            raise ContractValidationError(
                f"schema_version missing at {selected_path}; pass --schema for YAML contracts"
            )
        schema_id = detected_schema_id

    contract = SCHEMA_CONTRACTS_BY_ID.get(schema_id)
    if contract is None:
        available = ", ".join(sorted(SCHEMA_CONTRACTS_BY_ID))
        raise ContractValidationError(
            f"unknown schema contract {schema_id!r}; available: {available}"
        )

    try:
        if schema_id in {SCENARIO_SCHEMA_VERSION, RELEASE_CONTRACT_SCHEMA_VERSION}:
            contract.model.model_validate(_read_yaml_payload(selected_path))
        else:
            contract.model.model_validate(_read_json_payload(selected_path))
    except (OSError, ValidationError, yaml.YAMLError, json.JSONDecodeError) as error:
        raise ContractValidationError(
            f"invalid {schema_id} contract at {selected_path}: {error}"
        ) from error
    return schema_id


def validate_schema_contract_dir(
    path: str | Path,
    *,
    schema_id: str | None = None,
    patterns: tuple[str, ...] = ("*.json",),
    recursive: bool = False,
) -> SchemaDirectoryValidationResult:
    selected_path = Path(path)
    if not selected_path.is_dir():
        raise ContractValidationError(f"schema validate-dir requires a directory: {selected_path}")
    if not patterns:
        raise ContractValidationError("schema validate-dir requires at least one --pattern")

    matched_paths = _matched_contract_paths(selected_path, patterns, recursive=recursive)
    if not matched_paths:
        rendered_patterns = ", ".join(patterns)
        raise ContractValidationError(f"no files matched {rendered_patterns} under {selected_path}")

    records: list[SchemaValidationRecord] = []
    for matched_path in matched_paths:
        try:
            validated_schema_id = validate_schema_contract(matched_path, schema_id=schema_id)
        except ContractValidationError as error:
            records.append(
                SchemaValidationRecord(path=matched_path, schema_id=schema_id, error=str(error))
            )
        else:
            records.append(SchemaValidationRecord(path=matched_path, schema_id=validated_schema_id))
    return SchemaDirectoryValidationResult(root=selected_path, records=tuple(records))


def _matched_contract_paths(
    root: Path,
    patterns: tuple[str, ...],
    *,
    recursive: bool,
) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in patterns:
        matches = root.rglob(pattern) if recursive else root.glob(pattern)
        paths.update(path for path in matches if path.is_file())
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def _read_json_payload(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractValidationError(f"cannot read contract at {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ContractValidationError(f"invalid JSON contract at {path}: {error}") from error


def _read_yaml_payload(path: Path) -> Any:
    try:
        return load_bounded_yaml(path)
    except OSError as error:
        raise ContractValidationError(f"cannot read contract at {path}: {error}") from error
    except ContractYamlError as error:
        raise ContractValidationError(f"invalid YAML contract at {path}: {error}") from error
