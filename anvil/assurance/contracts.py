from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
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
from anvil.assurance.evidence import (
    NAMESPACED_TYPE_PATTERN,
    EvidenceRequirement,
)
from anvil.assurance.identity import (
    MANDATORY_COMPONENT_KINDS,
    ReleaseComponent,
    release_identity,
    validate_release_components,
)
from anvil.assurance.yaml import DEFAULT_MAX_YAML_BYTES, ContractYamlError, load_bounded_yaml

RELEASE_CONTRACT_SCHEMA_VERSION = "assurance.anvil.dev/release-contract/v1alpha1"
MAX_RELEASE_CONTRACT_BYTES = DEFAULT_MAX_YAML_BYTES
_RELEASE_COMPONENT_CARDINALITY_SCHEMA: dict[str, Any] = {
    "allOf": [
        {
            "properties": {
                "components": {
                    "contains": {
                        "properties": {"kind": {"const": kind.value}},
                        "required": ["kind"],
                    },
                    "minContains": 1,
                    "maxContains": 1,
                }
            }
        }
        for kind in sorted(MANDATORY_COMPONENT_KINDS, key=lambda selected: selected.value)
    ]
}
_TASK_INPUT_CARDINALITY_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {
            "required": ["input"],
            "not": {"required": ["inputRef"]},
        },
        {
            "required": ["inputRef"],
            "not": {"required": ["input"]},
            "properties": {"inputRef": {"type": "string", "minLength": 1}},
        },
    ]
}


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
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_RELEASE_COMPONENT_CARDINALITY_SCHEMA,
    )

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
    model_config = ConfigDict(
        validate_by_alias=True,
        validate_by_name=False,
        extra="forbid",
        json_schema_extra=_TASK_INPUT_CARDINALITY_SCHEMA,
    )

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

    @field_validator("version")
    @classmethod
    def validate_version_specifier(cls, version: str) -> str:
        try:
            SpecifierSet(version)
        except InvalidSpecifier as error:
            raise ValueError("invalid pack version specifier") from error
        return version


class CheckDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonBlankStr
    type: str = Field(pattern=NAMESPACED_TYPE_PATTERN)
    config: dict[str, JsonValue] = Field(default_factory=dict)


class EvidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require: list[EvidenceRequirement] = Field(default_factory=list)


class ReliabilityPolicy(BaseModel):
    model_config = ConfigDict(validate_by_alias=True, validate_by_name=False, extra="forbid")

    trials: int = Field(default=1, ge=1, strict=True)
    minimum_pass_rate: float = Field(
        default=1.0,
        alias="minimumPassRate",
        ge=0.0,
        le=1.0,
        strict=True,
    )


class ReleaseContract(BaseModel):
    model_config = ConfigDict(validate_by_alias=True, validate_by_name=False, extra="forbid")

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


@dataclass(frozen=True)
class RegisteredPack:
    name: str
    version: Version
    check_types: Mapping[str, type[BaseModel]]


class CheckTypeRegistry:
    """Explicitly registered check types; contract data never drives imports."""

    def __init__(self) -> None:
        self._packs: dict[str, RegisteredPack] = {}
        self._check_type_owners: dict[str, str] = {}

    def register_pack(
        self,
        *,
        name: str,
        version: str,
        check_types: Mapping[str, type[BaseModel]],
    ) -> None:
        if name in self._packs:
            raise AssuranceError(
                "pack is already registered",
                code="check_config_error",
                path="$.packs",
                details={"pack": name},
            )
        try:
            selected_version = Version(version)
        except InvalidVersion as error:
            raise AssuranceError(
                "registered pack version is invalid",
                code="check_config_error",
                path="$.packs",
                details={"pack": name},
            ) from error

        for check_type in check_types:
            if re.fullmatch(NAMESPACED_TYPE_PATTERN, check_type) is None:
                raise AssuranceError(
                    "registered check type is not namespaced and versioned",
                    code="check_config_error",
                    path="$.packs",
                    details={"check_type": check_type},
                )
            if check_type in self._check_type_owners:
                raise AssuranceError(
                    "check type already belongs to another pack",
                    code="check_config_error",
                    path="$.packs",
                    details={"check_type": check_type},
                )

        self._packs[name] = RegisteredPack(
            name=name,
            version=selected_version,
            check_types=dict(check_types),
        )
        self._check_type_owners.update(dict.fromkeys(check_types, name))

    def validate(self, contract: ReleaseContract) -> None:
        declared: dict[str, RegisteredPack] = {}
        for index, requirement in enumerate(contract.packs):
            pack = self._packs.get(requirement.name)
            if pack is None:
                raise AssuranceError(
                    "declared pack is not registered",
                    code="unknown_pack",
                    path=f"$.packs[{index}].name",
                    details={"pack": requirement.name},
                )
            if pack.version not in SpecifierSet(requirement.version):
                raise AssuranceError(
                    "registered pack version is incompatible",
                    code="incompatible_pack",
                    path=f"$.packs[{index}].version",
                    details={"pack": requirement.name},
                )
            declared[pack.name] = pack

        for index, check in enumerate(contract.checks):
            owner_name = self._check_type_owners.get(check.type)
            owner = declared.get(owner_name) if owner_name is not None else None
            if owner is None:
                raise AssuranceError(
                    "check type is not owned by a declared compatible pack",
                    code="unknown_check_type",
                    path=f"$.checks[{index}].type",
                    details={"check_type": check.type},
                )
            config_model = owner.check_types[check.type]
            try:
                config_model.model_validate(check.config)
            except ValidationError as error:
                first_error = error.errors(include_input=False, include_url=False)[0]
                suffix = _validation_path(first_error.get("loc", ()))[1:]
                raise AssuranceError(
                    "check configuration does not match its registered schema",
                    code="check_config_error",
                    path=f"$.checks[{index}].config{suffix}",
                    details={"check_type": check.type},
                ) from None


def load_release_contract(
    path: str | Path, *, registry: CheckTypeRegistry | None = None
) -> ReleaseContract:
    selected_path = Path(path)
    try:
        payload = load_bounded_yaml(selected_path, max_bytes=MAX_RELEASE_CONTRACT_BYTES)
    except OSError:
        raise AssuranceError(
            "cannot read release contract",
            code="contract_parse_error",
            path="$",
        ) from None
    except ContractYamlError as error:
        raise AssuranceError(
            f"cannot parse release contract YAML: {error}",
            code="contract_parse_error",
            path="$",
        ) from None
    except yaml.YAMLError:
        raise AssuranceError(
            "cannot parse release contract YAML",
            code="contract_parse_error",
            path="$",
        ) from None

    if not isinstance(payload, dict):
        raise AssuranceError(
            "release contract must be a YAML mapping",
            code="contract_parse_error",
            path="$",
        )

    try:
        contract = ReleaseContract.model_validate(payload)
    except ValidationError as error:
        first_error = error.errors(include_input=False, include_url=False)[0]
        raise AssuranceError(
            "release contract does not match its schema",
            code="contract_schema_error",
            path=_validation_path(first_error.get("loc", ())),
            details={"validation_type": str(first_error.get("type", "unknown"))},
        ) from None
    if registry is not None:
        registry.validate(contract)
    return contract


def _validation_path(location: Any) -> str:
    path = "$"
    for part in location:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(part, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
            path += f".{part}"
        else:
            path += f"[{json.dumps(str(part), ensure_ascii=True)}]"
    return path
