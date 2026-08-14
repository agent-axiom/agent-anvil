from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from anvil.assurance.errors import AssuranceError
from anvil.assurance.identity import (
    ReleaseComponent,
    release_identity,
    validate_release_components,
)

RELEASE_CONTRACT_SCHEMA_VERSION = "assurance.anvil.dev/release-contract/v1alpha1"
NAMESPACED_TYPE_PATTERN = r"^(?:[a-z][a-z0-9_-]*\.)+[a-z][a-z0-9_-]*\.v[1-9][0-9]*$"


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankStr = Annotated[str, Field(min_length=1), AfterValidator(_non_blank)]


class ContractSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContractMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonBlankStr
    severity: ContractSeverity
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("labels")
    @classmethod
    def reject_blank_labels(cls, labels: dict[str, str]) -> dict[str, str]:
        if any(not key.strip() or not value.strip() for key, value in labels.items()):
            raise ValueError("label names and values must not be blank")
        return labels


class ReleaseDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: list[ReleaseComponent] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_component_set(self) -> ReleaseDefinition:
        validate_release_components(self.components)
        return self


class ActorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: NonBlankStr
    permissions: list[NonBlankStr] = Field(default_factory=list)

    @field_validator("permissions")
    @classmethod
    def reject_duplicate_permissions(cls, permissions: list[str]) -> list[str]:
        if len(set(permissions)) != len(permissions):
            raise ValueError("duplicate permissions are not allowed")
        return permissions


class TaskDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    input: JsonValue | None = None
    input_ref: NonBlankStr | None = Field(default=None, alias="inputRef")

    @model_validator(mode="after")
    def require_exactly_one_input(self) -> TaskDefinition:
        supplied = {"input", "input_ref"}.intersection(self.model_fields_set)
        if len(supplied) != 1 or ("input_ref" in supplied and self.input_ref is None):
            raise ValueError("task requires exactly one of input or inputRef")
        return self


class PackRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonBlankStr
    version: NonBlankStr


class CheckDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonBlankStr
    type: str = Field(pattern=NAMESPACED_TYPE_PATTERN)
    config: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: str = Field(pattern=NAMESPACED_TYPE_PATTERN)
    minimum_trust: Literal["L0", "L1", "L2", "L3"] = Field(alias="minimumTrust")
    subject: NonBlankStr | None = None
    minimum_count: int = Field(default=1, alias="minimumCount", ge=1)


class EvidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require: list[EvidenceRequirement] = Field(default_factory=list)


class ReliabilityPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    trials: int = Field(default=1, ge=1)
    minimum_pass_rate: float = Field(default=1.0, alias="minimumPassRate", ge=0.0, le=1.0)


class ReleaseContract(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_version: Literal["assurance.anvil.dev/release-contract/v1alpha1"] = Field(
        alias="apiVersion"
    )
    kind: Literal["ReleaseContract"]
    metadata: ContractMetadata
    release: ReleaseDefinition
    actor: ActorDefinition
    task: TaskDefinition
    packs: list[PackRequirement] = Field(default_factory=list)
    checks: list[CheckDefinition] = Field(default_factory=list)
    evidence: EvidencePolicy = Field(default_factory=EvidencePolicy)
    reliability: ReliabilityPolicy = Field(default_factory=ReliabilityPolicy)

    @model_validator(mode="after")
    def reject_duplicate_entries(self) -> ReleaseContract:
        pack_names = [pack.name for pack in self.packs]
        if len(set(pack_names)) != len(pack_names):
            raise ValueError("duplicate packs are not allowed")
        check_ids = [check.id for check in self.checks]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("duplicate checks are not allowed")
        return self

    @property
    def release_id(self) -> str:
        return release_identity(self.release.components)


def load_release_contract(path: str | Path) -> ReleaseContract:
    selected_path = Path(path)
    try:
        payload = yaml.safe_load(selected_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise AssuranceError(
            "cannot read release contract",
            code="contract_parse_error",
            path="$",
        ) from error
    except yaml.YAMLError as error:
        raise AssuranceError(
            "cannot parse release contract YAML",
            code="contract_parse_error",
            path="$",
        ) from error

    if not isinstance(payload, dict):
        raise AssuranceError(
            "release contract must be a YAML mapping",
            code="contract_parse_error",
            path="$",
        )

    try:
        return ReleaseContract.model_validate(payload)
    except ValidationError as error:
        first_error = error.errors(include_input=False, include_url=False)[0]
        raise AssuranceError(
            "release contract does not match its schema",
            code="contract_schema_error",
            path=_validation_path(first_error.get("loc", ())),
            details={"validation_type": str(first_error.get("type", "unknown"))},
        ) from error


def _validation_path(location: Any) -> str:
    path = "$"
    for part in location:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path
