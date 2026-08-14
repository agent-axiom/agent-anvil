from __future__ import annotations

import copy
import importlib
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from pytest_mock import MockerFixture

from anvil.assurance.contracts import (
    CheckTypeRegistry,
    ReleaseContract,
    load_release_contract,
)
from anvil.assurance.errors import AssuranceError


class RowCountConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(min_length=1)
    where: dict[str, JsonValue] = Field(default_factory=dict)
    equals: int = Field(ge=0)


def postgres_registry() -> CheckTypeRegistry:
    registry = CheckTypeRegistry()
    registry.register_pack(
        name="anvil-pack-postgres",
        version="0.1.4",
        check_types={"postgres.row_count.v1": RowCountConfig},
    )
    return registry


def test_pack_registry_validates_compatible_owned_check(
    valid_release_contract_payload: dict[str, object],
) -> None:
    contract = ReleaseContract.model_validate(valid_release_contract_payload)

    postgres_registry().validate(contract)


def test_load_release_contract_applies_supplied_registry(
    tmp_path: Path, valid_release_contract_payload: dict[str, object]
) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(valid_release_contract_payload), encoding="utf-8")

    contract = load_release_contract(path, registry=postgres_registry())

    assert contract.checks[0].type == "postgres.row_count.v1"


def test_pack_registry_rejects_unknown_declared_pack(
    valid_release_contract_payload: dict[str, object],
) -> None:
    contract = ReleaseContract.model_validate(valid_release_contract_payload)

    with pytest.raises(AssuranceError) as captured:
        CheckTypeRegistry().validate(contract)

    assert captured.value.code == "unknown_pack"
    assert captured.value.path == "$.packs[0].name"


def test_pack_registry_rejects_incompatible_installed_version(
    valid_release_contract_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    packs = payload["packs"]
    assert isinstance(packs, list)
    assert isinstance(packs[0], dict)
    packs[0]["version"] = ">=0.2"
    contract = ReleaseContract.model_validate(payload)

    with pytest.raises(AssuranceError) as captured:
        postgres_registry().validate(contract)

    assert captured.value.code == "incompatible_pack"
    assert captured.value.path == "$.packs[0].version"


def test_release_contract_rejects_invalid_pack_specifier(
    valid_release_contract_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    packs = payload["packs"]
    assert isinstance(packs, list)
    assert isinstance(packs[0], dict)
    packs[0]["version"] = "not a specifier!"

    with pytest.raises(ValidationError, match="invalid pack version specifier"):
        ReleaseContract.model_validate(payload)


def test_pack_registry_rejects_unknown_check_type_from_declared_pack(
    valid_release_contract_payload: dict[str, object],
) -> None:
    registry = CheckTypeRegistry()
    registry.register_pack(name="anvil-pack-postgres", version="0.1.4", check_types={})
    contract = ReleaseContract.model_validate(valid_release_contract_payload)

    with pytest.raises(AssuranceError) as captured:
        registry.validate(contract)

    assert captured.value.code == "unknown_check_type"
    assert captured.value.path == "$.checks[0].type"


def test_pack_registry_rejects_check_owned_by_undeclared_pack(
    valid_release_contract_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload["packs"] = []
    contract = ReleaseContract.model_validate(payload)

    with pytest.raises(AssuranceError) as captured:
        postgres_registry().validate(contract)

    assert captured.value.code == "unknown_check_type"
    assert captured.value.path == "$.checks[0].type"


@pytest.mark.parametrize(
    ("config", "expected_path"),
    [
        ({"table": "public.refunds"}, "$.checks[0].config.equals"),
        (
            {"table": "public.refunds", "equals": 1, "sql": "DELETE FROM refunds"},
            "$.checks[0].config.sql",
        ),
    ],
)
def test_pack_registry_rejects_invalid_pack_specific_config(
    valid_release_contract_payload: dict[str, object],
    config: dict[str, object],
    expected_path: str,
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    checks = payload["checks"]
    assert isinstance(checks, list)
    assert isinstance(checks[0], dict)
    checks[0]["config"] = config
    contract = ReleaseContract.model_validate(payload)

    with pytest.raises(AssuranceError) as captured:
        postgres_registry().validate(contract)

    assert captured.value.code == "check_config_error"
    assert captured.value.path == expected_path


def test_pack_registry_rejects_duplicate_pack_registration() -> None:
    registry = postgres_registry()

    with pytest.raises(AssuranceError) as captured:
        registry.register_pack(
            name="anvil-pack-postgres",
            version="0.1.5",
            check_types={"postgres.row_count.v1": RowCountConfig},
        )

    assert captured.value.code == "check_config_error"
    assert captured.value.path == "$.packs"


@pytest.mark.parametrize("version", ["not a version", "", "v1..2"])
def test_pack_registry_rejects_invalid_installed_version(version: str) -> None:
    registry = CheckTypeRegistry()

    with pytest.raises(AssuranceError) as captured:
        registry.register_pack(name="pack", version=version, check_types={})

    assert captured.value.code == "check_config_error"


def test_pack_registry_rejects_duplicate_check_type_ownership() -> None:
    registry = postgres_registry()

    with pytest.raises(AssuranceError) as captured:
        registry.register_pack(
            name="another-pack",
            version="1.0.0",
            check_types={"postgres.row_count.v1": RowCountConfig},
        )

    assert captured.value.code == "check_config_error"
    assert captured.value.details == {"check_type": "postgres.row_count.v1"}


def test_pack_registry_never_imports_pack_name_from_contract(
    valid_release_contract_payload: dict[str, object], mocker: MockerFixture
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    packs = payload["packs"]
    assert isinstance(packs, list)
    assert isinstance(packs[0], dict)
    packs[0]["name"] = "attacker.controlled.package"
    contract = ReleaseContract.model_validate(payload)
    import_module = mocker.patch.object(importlib, "import_module")

    with pytest.raises(AssuranceError, match="unknown_pack"):
        CheckTypeRegistry().validate(contract)

    import_module.assert_not_called()
