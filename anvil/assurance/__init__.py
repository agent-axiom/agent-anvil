"""Release-assurance contracts and integrity primitives."""

from anvil.assurance.canonical import canonical_json_bytes, sha256_bytes, sha256_json
from anvil.assurance.contracts import (
    RELEASE_CONTRACT_SCHEMA_VERSION,
    CheckTypeRegistry,
    ReleaseContract,
    load_release_contract,
)
from anvil.assurance.errors import AssuranceError
from anvil.assurance.evidence import (
    EVIDENCE_RECORD_SCHEMA_VERSION,
    EvidenceRecord,
    EvidenceRequirement,
    EvidenceTrustPolicy,
    TrustAssignment,
    TrustLevel,
    VerifiedContent,
    VerifiedEvidence,
    VerifiedTrust,
    evidence_identity,
    verify_evidence_content,
    verify_evidence_identity,
    verify_evidence_record,
    verify_evidence_trust,
)
from anvil.assurance.identity import (
    MANDATORY_COMPONENT_KINDS,
    ComponentKind,
    ReleaseComponent,
    release_identity,
    validate_release_components,
)

__all__ = [
    "EVIDENCE_RECORD_SCHEMA_VERSION",
    "MANDATORY_COMPONENT_KINDS",
    "RELEASE_CONTRACT_SCHEMA_VERSION",
    "AssuranceError",
    "CheckTypeRegistry",
    "ComponentKind",
    "EvidenceRecord",
    "EvidenceRequirement",
    "EvidenceTrustPolicy",
    "ReleaseComponent",
    "ReleaseContract",
    "TrustAssignment",
    "TrustLevel",
    "VerifiedContent",
    "VerifiedEvidence",
    "VerifiedTrust",
    "canonical_json_bytes",
    "evidence_identity",
    "load_release_contract",
    "release_identity",
    "sha256_bytes",
    "sha256_json",
    "validate_release_components",
    "verify_evidence_content",
    "verify_evidence_identity",
    "verify_evidence_record",
    "verify_evidence_trust",
]
