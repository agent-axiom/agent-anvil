from __future__ import annotations

import hashlib
import heapq
import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
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


class ObservedEvidenceSource(BaseModel):
    """Source identity supplied by the trusted ingestion boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


@dataclass(frozen=True)
class VerifiedContent:
    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, init=False)
class VerifiedEvidence:
    record: EvidenceRecord
    assigned_trust: TrustLevel
    content: VerifiedContent


def _create_verified_evidence(
    *,
    record: EvidenceRecord,
    assigned_trust: TrustLevel,
    content: VerifiedContent,
) -> VerifiedEvidence:
    verified = object.__new__(VerifiedEvidence)
    object.__setattr__(verified, "record", record)
    object.__setattr__(verified, "assigned_trust", assigned_trust)
    object.__setattr__(verified, "content", content)
    return verified


@dataclass(frozen=True)
class EvidenceRequirementMatch:
    requirement: EvidenceRequirement
    evidence_ids: tuple[str, ...]

    @property
    def satisfied(self) -> bool:
        return len(self.evidence_ids) >= self.requirement.minimum_count


def evidence_identity(value: EvidenceRecord | Mapping[str, Any]) -> str:
    if isinstance(value, EvidenceRecord):
        payload = value.model_dump(mode="json", by_alias=True)
    else:
        payload = dict(value)
    payload.pop("evidenceId", None)
    payload.pop("evidence_id", None)
    parents = payload.get("parents")
    if isinstance(parents, list) and all(isinstance(parent, str) for parent in parents):
        payload["parents"] = sorted(parents)
    return sha256_json(payload)


def verify_evidence_identity(record: EvidenceRecord) -> None:
    expected = evidence_identity(record)
    if not hmac.compare_digest(record.evidence_id, expected):
        raise AssuranceError(
            "evidence metadata digest does not match evidenceId",
            code="evidence_digest_mismatch",
            path="$.evidenceId",
        )


def verify_evidence_trust(
    record: EvidenceRecord,
    policy: EvidenceTrustPolicy,
    *,
    observed_source: ObservedEvidenceSource,
) -> VerifiedTrust:
    record_source_key = (record.source.collector, record.source.version, record.source.boundary)
    source_key = (
        observed_source.collector,
        observed_source.version,
        observed_source.boundary,
    )
    if record_source_key != source_key:
        raise AssuranceError(
            "evidence source does not match the trusted ingestion observation",
            code="evidence_trust_error",
            path="$.source",
        )
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


def verify_evidence_content(record: EvidenceRecord, store_root: Path) -> VerifiedContent:
    try:
        root = store_root.resolve(strict=True)
    except OSError as error:
        raise AssuranceError(
            "evidence store is missing",
            code="evidence_content_missing",
            path="$.content.path",
        ) from error

    raw_path = record.content.path
    relative = PurePosixPath(raw_path)
    if (
        "\\" in raw_path
        or relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or relative.as_posix() != raw_path
    ):
        raise AssuranceError(
            "evidence content path is not a normalized relative POSIX path",
            code="evidence_path_escape",
            path="$.content.path",
        )

    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError as error:
        raise AssuranceError(
            "evidence content is missing",
            code="evidence_content_missing",
            path="$.content.path",
        ) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise AssuranceError(
            "evidence content path escapes the store",
            code="evidence_path_escape",
            path="$.content.path",
        ) from error

    if not resolved.is_file():
        raise AssuranceError(
            "evidence content is not a regular file",
            code="evidence_content_missing",
            path="$.content.path",
        )

    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with resolved.open("rb") as content_file:
            while chunk := content_file.read(1024 * 1024):
                size_bytes += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise AssuranceError(
            "evidence content cannot be read",
            code="evidence_content_missing",
            path="$.content.path",
        ) from error

    if size_bytes != record.content.size_bytes:
        raise AssuranceError(
            "evidence content size does not match its record",
            code="evidence_digest_mismatch",
            path="$.content.sizeBytes",
        )
    selected_digest = digest.hexdigest()
    if not hmac.compare_digest(selected_digest, record.content.sha256):
        raise AssuranceError(
            "evidence content digest does not match its record",
            code="evidence_digest_mismatch",
            path="$.content.sha256",
        )
    return VerifiedContent(path=resolved, size_bytes=size_bytes, sha256=selected_digest)


def verify_evidence_record(
    record: EvidenceRecord,
    *,
    expected_release_id: str,
    expected_contract_id: str,
    observed_source: ObservedEvidenceSource,
    trust_policy: EvidenceTrustPolicy,
    store_root: Path,
) -> VerifiedEvidence:
    verify_evidence_identity(record)
    if not hmac.compare_digest(record.release_id, expected_release_id):
        raise AssuranceError(
            "evidence belongs to a different release",
            code="evidence_schema_error",
            path="$.releaseId",
        )
    if not hmac.compare_digest(record.contract_id, expected_contract_id):
        raise AssuranceError(
            "evidence belongs to a different assurance contract",
            code="evidence_schema_error",
            path="$.contractId",
        )
    trust = verify_evidence_trust(
        record,
        trust_policy,
        observed_source=observed_source,
    )
    content = verify_evidence_content(record, store_root)
    return _create_verified_evidence(
        record=record,
        assigned_trust=trust.assigned_trust,
        content=content,
    )


def validate_evidence_graph(records: Sequence[EvidenceRecord]) -> tuple[EvidenceRecord, ...]:
    records_by_id: dict[str, EvidenceRecord] = {}
    for record in records:
        if record.evidence_id in records_by_id:
            raise AssuranceError(
                "evidence graph contains duplicate record identifiers",
                code="evidence_schema_error",
                path="$.evidenceId",
            )
        records_by_id[record.evidence_id] = record

    children = {evidence_id: [] for evidence_id in records_by_id}
    indegree = dict.fromkeys(records_by_id, 0)
    for record in records_by_id.values():
        if len(set(record.parents)) != len(record.parents):
            raise AssuranceError(
                "evidence graph contains duplicate parent identifiers",
                code="evidence_schema_error",
                path="$.parents",
            )
        if record.evidence_id in record.parents:
            raise AssuranceError(
                "evidence graph contains a self-parent relationship",
                code="evidence_schema_error",
                path="$.parents",
            )
        for parent in record.parents:
            if parent not in records_by_id:
                raise AssuranceError(
                    "evidence graph contains a dangling parent",
                    code="evidence_schema_error",
                    path="$.parents",
                )
            children[parent].append(record.evidence_id)
            indegree[record.evidence_id] += 1

    ready = [evidence_id for evidence_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered_ids: list[str] = []
    while ready:
        evidence_id = heapq.heappop(ready)
        ordered_ids.append(evidence_id)
        for child in sorted(children[evidence_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)

    if len(ordered_ids) != len(records_by_id):
        raise AssuranceError(
            "evidence graph contains a cycle",
            code="evidence_graph_cycle",
            path="$.parents",
        )
    return tuple(records_by_id[evidence_id] for evidence_id in ordered_ids)


def match_evidence_requirement(
    requirement: EvidenceRequirement,
    evidence: Sequence[VerifiedEvidence],
) -> EvidenceRequirementMatch:
    if any(not isinstance(item, VerifiedEvidence) for item in evidence):
        raise TypeError("evidence requirements can only be matched against VerifiedEvidence")
    matching_ids = {
        item.record.evidence_id
        for item in evidence
        if item.record.type == requirement.type
        and (requirement.subject is None or item.record.subject == requirement.subject)
        and item.assigned_trust.rank >= requirement.minimum_trust.rank
    }
    return EvidenceRequirementMatch(
        requirement=requirement,
        evidence_ids=tuple(sorted(matching_ids)),
    )


def match_evidence_requirements(
    requirements: Sequence[EvidenceRequirement],
    evidence: Sequence[VerifiedEvidence],
) -> tuple[EvidenceRequirementMatch, ...]:
    return tuple(match_evidence_requirement(requirement, evidence) for requirement in requirements)


def _is_prefixed_sha256(value: str) -> bool:
    return (
        len(value) == PREFIXED_SHA256_LENGTH
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
