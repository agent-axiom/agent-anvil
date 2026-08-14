"""Release-assurance contracts and integrity primitives."""

from anvil.assurance.canonical import canonical_json_bytes, sha256_bytes, sha256_json
from anvil.assurance.contracts import (
    RELEASE_CONTRACT_SCHEMA_VERSION,
    ReleaseContract,
    load_release_contract,
)
from anvil.assurance.errors import AssuranceError
from anvil.assurance.identity import (
    MANDATORY_COMPONENT_KINDS,
    ComponentKind,
    ReleaseComponent,
    release_identity,
    validate_release_components,
)

__all__ = [
    "MANDATORY_COMPONENT_KINDS",
    "RELEASE_CONTRACT_SCHEMA_VERSION",
    "AssuranceError",
    "ComponentKind",
    "ReleaseComponent",
    "ReleaseContract",
    "canonical_json_bytes",
    "load_release_contract",
    "release_identity",
    "sha256_bytes",
    "sha256_json",
    "validate_release_components",
]
