from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from anvil.assurance.canonical import sha256_json
from anvil.assurance.errors import AssuranceError

SHA256_PREFIXED_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ComponentKind(StrEnum):
    AGENT_CODE = "agent_code"
    MODEL_CONFIG = "model_config"
    PROMPT_BUNDLE = "prompt_bundle"
    TOOL_SCHEMA = "tool_schema"
    POLICY = "policy"
    ENVIRONMENT = "environment"
    ADAPTER = "adapter"
    MEMORY_SCHEMA = "memory_schema"


MANDATORY_COMPONENT_KINDS = frozenset(
    {
        ComponentKind.AGENT_CODE,
        ComponentKind.MODEL_CONFIG,
        ComponentKind.PROMPT_BUNDLE,
        ComponentKind.TOOL_SCHEMA,
        ComponentKind.POLICY,
        ComponentKind.ENVIRONMENT,
    }
)


class ReleaseComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ComponentKind
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    digest: str = Field(pattern=SHA256_PREFIXED_PATTERN)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("name", "version")
    @classmethod
    def reject_blank_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def validate_release_components(components: Sequence[ReleaseComponent]) -> None:
    component_counts = Counter((component.kind, component.name) for component in components)
    duplicate_components = sorted(
        f"{kind.value}:{name}" for (kind, name), count in component_counts.items() if count > 1
    )
    if duplicate_components:
        raise AssuranceError(
            "release contains duplicate components",
            code="release_identity_incomplete",
            path="$.release.components",
            details={"duplicate_components": duplicate_components},
        )

    kind_counts = Counter(component.kind for component in components)
    missing = sorted(kind.value for kind in MANDATORY_COMPONENT_KINDS if kind_counts[kind] == 0)
    if missing:
        raise AssuranceError(
            "release is missing mandatory components",
            code="release_identity_incomplete",
            path="$.release.components",
            details={"missing": missing},
        )

    duplicate_mandatory_kinds = sorted(
        kind.value for kind in MANDATORY_COMPONENT_KINDS if kind_counts[kind] > 1
    )
    if duplicate_mandatory_kinds:
        raise AssuranceError(
            "release contains multiple components for a mandatory kind",
            code="release_identity_incomplete",
            path="$.release.components",
            details={"duplicate_mandatory_kinds": duplicate_mandatory_kinds},
        )


def release_identity(components: Sequence[ReleaseComponent]) -> str:
    """Hash the behavior-bearing component identity, independent of document order."""
    validate_release_components(components)
    canonical_components = sorted(
        (
            {
                "digest": component.digest,
                "kind": component.kind.value,
                "name": component.name,
                "version": component.version,
            }
            for component in components
        ),
        key=lambda item: (item["kind"], item["name"], item["version"], item["digest"]),
    )
    return sha256_json({"components": canonical_components})
