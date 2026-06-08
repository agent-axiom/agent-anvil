from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from anvil.doctor import DOCTOR_REPORT_SCHEMA_VERSION, DoctorReportPayload
from anvil.leaderboard import (
    LEADERBOARD_AUDIT_SCHEMA_VERSION,
    LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION,
    LEADERBOARD_INDEX_SCHEMA_VERSION,
    LEADERBOARD_SCHEMA_VERSION,
    LeaderboardAuditReport,
    LeaderboardGithubRunVerification,
    LeaderboardIndex,
    LeaderboardSubmission,
)
from anvil.runner import COMPARE_RESULT_SCHEMA_VERSION, CompareResultPayload
from anvil.scenario import ScenarioSuite
from anvil.storage import RESULTS_SCHEMA_VERSION, ResultsPayload
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


SCHEMA_CONTRACTS: tuple[SchemaContract, ...] = (
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
        schema_id=LEADERBOARD_AUDIT_SCHEMA_VERSION,
        filename="agent-anvil.leaderboard.audit.v1.schema.json",
        model=LeaderboardAuditReport,
        description="Agent Anvil public leaderboard maintainer audit report schema.",
    ),
)


def contract_schema(contract: SchemaContract) -> dict[str, Any]:
    schema = contract.model.model_json_schema(mode="validation")
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
