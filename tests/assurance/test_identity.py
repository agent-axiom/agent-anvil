from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from anvil.assurance.errors import AssuranceError
from anvil.assurance.identity import (
    ComponentKind,
    ReleaseComponent,
    release_identity,
    validate_release_components,
)


def test_release_identity_is_independent_of_component_order(
    release_components: list[ReleaseComponent],
) -> None:
    assert release_identity(release_components) == release_identity(
        list(reversed(release_components))
    )


def test_release_identity_is_independent_of_descriptive_metadata(
    release_components: list[ReleaseComponent], tmp_path: Path
) -> None:
    with_metadata = [component.model_copy(deep=True) for component in release_components]
    with_metadata[0] = with_metadata[0].model_copy(
        update={"metadata": {"checkout": str(tmp_path), "owner": "payments"}}
    )

    assert release_identity(with_metadata) == release_identity(release_components)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("name", "changed-agent"),
        ("version", "v999"),
        ("digest", f"sha256:{'f' * 64}"),
    ],
)
def test_release_identity_changes_for_behavior_fields(
    release_components: list[ReleaseComponent], field: str, replacement: str
) -> None:
    baseline = release_identity(release_components)
    changed = [component.model_copy(deep=True) for component in release_components]
    changed[0] = changed[0].model_copy(update={field: replacement})

    assert release_identity(changed) != baseline


@pytest.mark.parametrize(
    "digest",
    [
        "0" * 64,
        f"sha256:{'A' * 64}",
        f"sha256:{'a' * 63}",
        f"sha512:{'a' * 64}",
    ],
)
def test_release_component_rejects_noncanonical_digest(digest: str) -> None:
    with pytest.raises(ValidationError):
        ReleaseComponent(
            kind=ComponentKind.AGENT_CODE,
            name="agent",
            version="v1",
            digest=digest,
        )


def test_release_component_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReleaseComponent.model_validate(
            {
                "kind": "agent_code",
                "name": "agent",
                "version": "v1",
                "digest": f"sha256:{'a' * 64}",
                "local_path": "/tmp/agent",
            }
        )


@pytest.mark.parametrize(("field", "value"), [("name", "  "), ("version", "\t")])
def test_release_component_rejects_blank_identifiers(field: str, value: str) -> None:
    payload = {
        "kind": "agent_code",
        "name": "agent",
        "version": "v1",
        "digest": f"sha256:{'a' * 64}",
    }
    payload[field] = value

    with pytest.raises(ValidationError, match="must not be blank"):
        ReleaseComponent.model_validate(payload)


def test_release_identity_rejects_missing_mandatory_kind(
    release_components: list[ReleaseComponent],
) -> None:
    incomplete = [
        component
        for component in release_components
        if component.kind is not ComponentKind.ENVIRONMENT
    ]

    with pytest.raises(AssuranceError) as captured:
        release_identity(incomplete)

    assert captured.value.code == "release_identity_incomplete"
    assert captured.value.path == "$.release.components"
    assert captured.value.details == {"missing": ["environment"]}


def test_release_identity_rejects_two_components_for_mandatory_kind(
    release_components: list[ReleaseComponent],
) -> None:
    duplicate_kind = [
        *release_components,
        release_components[0].model_copy(
            update={"name": "second-agent", "digest": f"sha256:{'e' * 64}"}
        ),
    ]

    with pytest.raises(AssuranceError) as captured:
        validate_release_components(duplicate_kind)

    assert captured.value.code == "release_identity_incomplete"
    assert captured.value.details == {"duplicate_mandatory_kinds": ["agent_code"]}


def test_release_identity_rejects_duplicate_component_key(
    release_components: list[ReleaseComponent],
) -> None:
    duplicate = [*release_components, release_components[-1].model_copy()]

    with pytest.raises(AssuranceError) as captured:
        validate_release_components(duplicate)

    assert captured.value.code == "release_identity_incomplete"
    assert captured.value.details == {"duplicate_components": ["environment:postgres-payments"]}


def test_release_identity_accepts_optional_components(
    release_components: list[ReleaseComponent],
) -> None:
    components = [
        *release_components,
        ReleaseComponent(
            kind=ComponentKind.ADAPTER,
            name="openai-responses-adapter",
            version="v2",
            digest=f"sha256:{'a' * 64}",
        ),
    ]

    assert release_identity(components).startswith("sha256:")
