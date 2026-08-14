from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from anvil.assurance.canonical import sha256_json
from anvil.assurance.errors import SECRET_DETAIL_KEYS, AssuranceError
from anvil.assurance.identity import SHA256_PREFIXED_PATTERN

EVIDENCE_RECORD_SCHEMA_VERSION = "assurance.anvil.dev/evidence-record/v1alpha1"
NAMESPACED_TYPE_PATTERN = r"^(?:[a-z][a-z0-9_-]*\.)+[a-z][a-z0-9_-]*\.v[1-9][0-9]*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
PREFIXED_SHA256_LENGTH = len("sha256:") + 64


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankStr = Annotated[str, Field(min_length=1), AfterValidator(_non_blank)]


class TrustLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"

    @property
    def rank(self) -> int:
        return int(self.value[1])


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collector: NonBlankStr
    version: NonBlankStr
    boundary: NonBlankStr | None = None


class EvidenceContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    media_type: NonBlankStr = Field(alias="mediaType")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    path: NonBlankStr


class EvidenceRedaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    applied: bool
    policy_digest: str | None = Field(
        default=None,
        alias="policyDigest",
        pattern=SHA256_PREFIXED_PATTERN,
    )

    @model_validator(mode="after")
    def require_policy_for_applied_redaction(self) -> EvidenceRedaction:
        if self.applied and self.policy_digest is None:
            raise ValueError("policyDigest is required when redaction is applied")
        return self


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: str = Field(pattern=NAMESPACED_TYPE_PATTERN)
    minimum_trust: TrustLevel = Field(alias="minimumTrust")
    subject: NonBlankStr | None = None
    minimum_count: int = Field(default=1, alias="minimumCount", ge=1)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Literal["assurance.anvil.dev/evidence-record/v1alpha1"] = Field(
        alias="schemaVersion"
    )
    evidence_id: str = Field(alias="evidenceId", pattern=SHA256_PREFIXED_PATTERN)
    run_id: NonBlankStr = Field(alias="runId")
    release_id: str = Field(alias="releaseId", pattern=SHA256_PREFIXED_PATTERN)
    contract_id: NonBlankStr = Field(alias="contractId")
    type: str = Field(pattern=NAMESPACED_TYPE_PATTERN)
    trust_level: TrustLevel = Field(alias="trustLevel")
    subject: NonBlankStr
    source: EvidenceSource
    observed_at: AwareDatetime = Field(alias="observedAt")
    content: EvidenceContent
    parents: list[str] = Field(default_factory=list)
    correlations: dict[str, NonBlankStr] = Field(default_factory=dict)
    redaction: EvidenceRedaction

    @field_validator("parents")
    @classmethod
    def validate_parent_digests(cls, parents: list[str]) -> list[str]:
        if any(_is_prefixed_sha256(parent) is False for parent in parents):
            raise ValueError("parents must contain prefixed SHA-256 identifiers")
        if len(set(parents)) != len(parents):
            raise ValueError("duplicate parent identifiers are not allowed")
        return parents

    @field_validator("correlations")
    @classmethod
    def reject_secret_correlations(
        cls, correlations: dict[str, str], info: ValidationInfo
    ) -> dict[str, str]:
        del info
        keys = {key.casefold() for key in correlations}
        if SECRET_DETAIL_KEYS.intersection(keys):
            raise ValueError("secret-like correlation keys are not allowed")
        if any(not key.strip() for key in correlations):
            raise ValueError("correlation keys must not be blank")
        return correlations

    @model_validator(mode="after")
    def validate_record_relationships(self) -> EvidenceRecord:
        if self.evidence_id in self.parents:
            raise ValueError("evidence cannot reference itself as a parent")
        if self.trust_level in {TrustLevel.L2, TrustLevel.L3} and self.source.boundary is None:
            raise ValueError("L2 and L3 evidence require an independent boundary")
        return self


class TrustAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collector: NonBlankStr
    version: NonBlankStr
    boundary: NonBlankStr | None = None
    maximum_trust: TrustLevel


class EvidenceTrustPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignments: list[TrustAssignment] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_assignments(self) -> EvidenceTrustPolicy:
        keys = [
            (assignment.collector, assignment.version, assignment.boundary)
            for assignment in self.assignments
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate trust assignments are not allowed")
        return self


@dataclass(frozen=True)
class VerifiedTrust:
    record: EvidenceRecord
    assigned_trust: TrustLevel


def evidence_identity(value: EvidenceRecord | Mapping[str, Any]) -> str:
    if isinstance(value, EvidenceRecord):
        payload = value.model_dump(mode="json", by_alias=True)
    else:
        payload = dict(value)
    payload.pop("evidenceId", None)
    payload.pop("evidence_id", None)
    return sha256_json(payload)


def verify_evidence_identity(record: EvidenceRecord) -> None:
    expected = evidence_identity(record)
    if not hmac.compare_digest(record.evidence_id, expected):
        raise AssuranceError(
            "evidence metadata digest does not match evidenceId",
            code="evidence_digest_mismatch",
            path="$.evidenceId",
        )


def verify_evidence_trust(record: EvidenceRecord, policy: EvidenceTrustPolicy) -> VerifiedTrust:
    source_key = (record.source.collector, record.source.version, record.source.boundary)
    assignment = next(
        (
            candidate
            for candidate in policy.assignments
            if (candidate.collector, candidate.version, candidate.boundary) == source_key
        ),
        None,
    )
    if assignment is None:
        raise AssuranceError(
            "evidence source has no trust assignment",
            code="evidence_trust_error",
            path="$.source",
            details={"collector": record.source.collector},
        )
    if record.trust_level.rank > assignment.maximum_trust.rank:
        raise AssuranceError(
            "claimed trust exceeds the configured assignment",
            code="evidence_trust_error",
            path="$.trustLevel",
            details={"collector": record.source.collector},
        )
    return VerifiedTrust(record=record, assigned_trust=record.trust_level)


def _is_prefixed_sha256(value: str) -> bool:
    return (
        len(value) == PREFIXED_SHA256_LENGTH
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
