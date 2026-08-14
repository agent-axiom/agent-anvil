from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from anvil.assurance.contracts import (
    MAX_RELEASE_CONTRACT_BYTES,
    RELEASE_CONTRACT_SCHEMA_VERSION,
    ReleaseContract,
    load_release_contract,
)
from anvil.assurance.errors import AssuranceError
from anvil.assurance.identity import release_identity
from anvil.assurance.yaml import ContractYamlError, load_bounded_yaml


def test_release_contract_round_trips_public_aliases(
    valid_release_contract_payload: dict[str, Any],
) -> None:
    contract = ReleaseContract.model_validate(valid_release_contract_payload)

    assert contract.api_version == RELEASE_CONTRACT_SCHEMA_VERSION
    assert contract.kind == "ReleaseContract"
    assert contract.release_id == release_identity(contract.release.components)
    assert contract.task.input_ref == "fixtures/refund-order-42.json"
    assert contract.evidence.require[0].minimum_trust == "L2"
    assert contract.reliability.minimum_pass_rate == 0.95
    dumped = contract.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert dumped["apiVersion"] == RELEASE_CONTRACT_SCHEMA_VERSION
    assert dumped["task"] == {"inputRef": "fixtures/refund-order-42.json"}
    assert dumped["evidence"]["require"][0]["minimumTrust"] == "L2"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("apiVersion", "assurance.anvil.dev/release-contract/v1"),
        ("kind", "ScenarioSuite"),
    ],
)
def test_release_contract_rejects_wrong_discriminators(
    valid_release_contract_payload: dict[str, Any], field: str, value: str
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload[field] = value

    with pytest.raises(ValidationError):
        ReleaseContract.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ["apiVersion", "kind", "metadata", "release", "actor", "task"],
)
def test_release_contract_rejects_missing_required_envelope_fields(
    valid_release_contract_payload: dict[str, Any], field: str
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    del payload[field]

    with pytest.raises(ValidationError, match="Field required"):
        ReleaseContract.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "extra_field"),
    [
        (None, "unexpected"),
        ("metadata", "repository"),
        ("release", "commit"),
        ("actor", "role"),
        ("task", "timeout"),
        ("evidence", "optional"),
        ("reliability", "confidence"),
    ],
)
def test_release_contract_rejects_unknown_fields_at_every_level(
    valid_release_contract_payload: dict[str, Any],
    section: str | None,
    extra_field: str,
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    target = payload if section is None else payload[section]
    assert isinstance(target, dict)
    target[extra_field] = "not-allowed"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReleaseContract.model_validate(payload)


@pytest.mark.parametrize(
    "task",
    [
        {},
        {"input": {"order_id": 42}, "inputRef": "fixtures/order.json"},
    ],
)
def test_release_contract_requires_exactly_one_task_input(
    valid_release_contract_payload: dict[str, Any], task: dict[str, Any]
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload["task"] = task

    with pytest.raises(ValidationError, match="exactly one of input or inputRef"):
        ReleaseContract.model_validate(payload)


def test_release_contract_rejects_blank_task_reference(
    valid_release_contract_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload["task"] = {"inputRef": "  "}

    with pytest.raises(ValidationError, match="must not be blank"):
        ReleaseContract.model_validate(payload)


def test_release_contract_accepts_inline_null_input(
    valid_release_contract_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload["task"] = {"input": None}

    contract = ReleaseContract.model_validate(payload)

    assert "input" in contract.task.model_fields_set
    assert contract.task.input is None


@pytest.mark.parametrize("collection", ["packs", "checks"])
def test_release_contract_rejects_duplicate_named_entries(
    valid_release_contract_payload: dict[str, Any], collection: str
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    entries = payload[collection]
    assert isinstance(entries, list)
    entries.append(copy.deepcopy(entries[0]))

    with pytest.raises(ValidationError, match=f"duplicate {collection}"):
        ReleaseContract.model_validate(payload)


@pytest.mark.parametrize(
    "invalid_type",
    ["row_count", "postgres.row_count", "postgres.row-count.v0", "Postgres.row_count.v1"],
)
def test_release_contract_rejects_unversioned_or_unnamespaced_types(
    valid_release_contract_payload: dict[str, Any], invalid_type: str
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    checks = payload["checks"]
    assert isinstance(checks, list)
    assert isinstance(checks[0], dict)
    checks[0]["type"] = invalid_type

    with pytest.raises(ValidationError):
        ReleaseContract.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trials", 0),
        ("minimumPassRate", -0.01),
        ("minimumPassRate", 1.01),
    ],
)
def test_release_contract_rejects_invalid_reliability_bounds(
    valid_release_contract_payload: dict[str, Any], field: str, value: object
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    reliability = payload["reliability"]
    assert isinstance(reliability, dict)
    reliability[field] = value

    with pytest.raises(ValidationError):
        ReleaseContract.model_validate(payload)


def test_release_contract_rejects_duplicate_mandatory_component_kind(
    valid_release_contract_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    release = payload["release"]
    assert isinstance(release, dict)
    components = release["components"]
    assert isinstance(components, list)
    duplicate = copy.deepcopy(components[0])
    assert isinstance(duplicate, dict)
    duplicate["name"] = "another-agent"
    components.append(duplicate)

    with pytest.raises(ValidationError, match="multiple components for a mandatory kind"):
        ReleaseContract.model_validate(payload)


def test_load_release_contract_reads_safe_yaml(
    tmp_path: Path, valid_release_contract_payload: dict[str, Any]
) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(valid_release_contract_payload), encoding="utf-8")

    contract = load_release_contract(path)

    assert contract.metadata.name == "refund-agent-postgres"


def test_load_release_contract_rejects_python_yaml_tags(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("!!python/object/apply:os.system ['echo unsafe']", encoding="utf-8")

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"
    assert "unsafe" not in str(captured.value)
    assert "os.system" not in str(captured.value)


def test_load_release_contract_normalizes_oversized_yaml_integer(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("value: " + "9" * 5_000 + "\n", encoding="utf-8")

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"
    assert captured.value.__cause__ is None


def test_load_release_contract_reports_schema_path_without_raw_input(
    tmp_path: Path, valid_release_contract_payload: dict[str, Any]
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["name"] = "  "
    metadata["token"] = "sk-must-not-leak"
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_schema_error"
    assert captured.value.path == "$.metadata.name"
    assert "sk-must-not-leak" not in str(captured.value)


def test_load_release_contract_escapes_untrusted_validation_path_and_drops_cause(
    tmp_path: Path, valid_release_contract_payload: dict[str, Any]
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload["evil\nline"] = "sk-must-not-leak"
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.path == '$["evil\\nline"]'
    assert captured.value.__cause__ is None
    assert "sk-must-not-leak" not in str(captured.value)


def test_load_release_contract_reports_missing_file_without_traceback(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"


def test_load_release_contract_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("- not\n- a\n- contract\n", encoding="utf-8")

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"


def test_load_release_contract_rejects_duplicate_yaml_keys(
    tmp_path: Path, valid_release_contract_payload: dict[str, Any]
) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(
        "kind: AttackerSelected\n" + yaml.safe_dump(valid_release_contract_payload),
        encoding="utf-8",
    )

    with pytest.raises(AssuranceError, match="duplicate YAML key") as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"


def test_load_release_contract_rejects_yaml_aliases(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("first: &shared [one]\nsecond: *shared\n", encoding="utf-8")

    with pytest.raises(AssuranceError, match="YAML aliases") as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"


def test_load_release_contract_rejects_tagged_non_string_mapping_keys(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("foo: first\n!!binary Zm9v: second\n", encoding="utf-8")

    with pytest.raises(AssuranceError, match="mapping keys must be strings") as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"


@pytest.mark.parametrize(
    ("payload", "options", "message"),
    [
        ("items: [one, two, three]\n", {"max_nodes": 3}, "too many nodes"),
        ("items:\n  - nested:\n      - value\n", {"max_depth": 3}, "nesting is too deep"),
    ],
)
def test_bounded_yaml_enforces_structural_budgets(
    tmp_path: Path,
    payload: str,
    options: dict[str, int],
    message: str,
) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ContractYamlError, match=message):
        load_bounded_yaml(path, **options)


def test_bounded_yaml_opens_contract_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("value: safe\n", encoding="utf-8")
    real_open = os.open
    observed_flags: list[int] = []

    def recording_open(
        selected_path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed_flags.append(flags)
        if dir_fd is None:
            return real_open(selected_path, flags, mode)
        return real_open(selected_path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", recording_open)

    assert load_bounded_yaml(path) == {"value": "safe"}
    assert observed_flags
    assert observed_flags[0] & os.O_NONBLOCK


def test_bounded_yaml_rejects_non_regular_input(tmp_path: Path) -> None:
    with pytest.raises(ContractYamlError, match="regular file"):
        load_bounded_yaml(tmp_path)


def test_load_release_contract_rejects_oversized_input_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_bytes(b"x" * (MAX_RELEASE_CONTRACT_BYTES + 1))

    with pytest.raises(AssuranceError, match="exceeds the maximum encoded size") as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert captured.value.path == "$"
