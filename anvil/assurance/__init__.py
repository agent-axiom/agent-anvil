"""Release-assurance contracts and integrity primitives."""

from anvil.assurance.canonical import canonical_json_bytes, sha256_bytes, sha256_json
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
    "AssuranceError",
    "ComponentKind",
    "ReleaseComponent",
    "canonical_json_bytes",
    "release_identity",
    "sha256_bytes",
    "sha256_json",
    "validate_release_components",
]
