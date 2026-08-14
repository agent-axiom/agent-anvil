from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from jsonschema.protocols import Validator
from pydantic import ValidationError as PydanticValidationError

from anvil.assurance.contracts import ReleaseContract
from anvil.assurance.evidence import EvidenceRecord
from anvil.assurance.identity import MANDATORY_COMPONENT_KINDS, ComponentKind

RELEASE_SCHEMA = "assurance.anvil.dev.release-contract.v1alpha1.schema.json"
EVIDENCE_SCHEMA = "assurance.anvil.dev.evidence-record.v1alpha1.schema.json"


def _validator(filename: str) -> Validator:
    schema = json.loads(Path("schemas", filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _assert_rejected_by_schema_and_model(
    validator: Validator,
    model: type[ReleaseContract] | type[EvidenceRecord],
    payload: dict[str, Any],
) -> None:
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(payload)
    with pytest.raises(PydanticValidationError):
        model.model_validate(payload)


def test_public_assurance_schemas_accept_golden_payloads(
    valid_release_contract_payload: dict[str, Any],
    evidence_record_payload: dict[str, Any],
) -> None:
    _validator(RELEASE_SCHEMA).validate(valid_release_contract_payload)
    _validator(EVIDENCE_SCHEMA).validate(evidence_record_payload)


@pytest.mark.parametrize(
    "task",
    [
        {},
        {"input": {"orderId": 42}, "inputRef": "fixtures/order.json"},
        {"inputRef": None},
    ],
    ids=["neither", "both", "null-input-ref"],
)
def test_public_release_schema_enforces_exactly_one_task_input(
    valid_release_contract_payload: dict[str, Any],
    task: dict[str, Any],
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    payload["task"] = task

    _assert_rejected_by_schema_and_model(_validator(RELEASE_SCHEMA), ReleaseContract, payload)


@pytest.mark.parametrize("missing_kind", sorted(MANDATORY_COMPONENT_KINDS, key=str))
def test_public_release_schema_requires_every_mandatory_component(
    valid_release_contract_payload: dict[str, Any],
    missing_kind: ComponentKind,
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    release = payload["release"]
    assert isinstance(release, dict)
    components = release["components"]
    assert isinstance(components, list)
    release["components"] = [item for item in components if item["kind"] != missing_kind.value]

    _assert_rejected_by_schema_and_model(_validator(RELEASE_SCHEMA), ReleaseContract, payload)


@pytest.mark.parametrize("duplicate_kind", sorted(MANDATORY_COMPONENT_KINDS, key=str))
def test_public_release_schema_rejects_duplicate_mandatory_component_kinds(
    valid_release_contract_payload: dict[str, Any],
    duplicate_kind: ComponentKind,
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    release = payload["release"]
    assert isinstance(release, dict)
    components = release["components"]
    assert isinstance(components, list)
    duplicate = next(item for item in components if item["kind"] == duplicate_kind.value)
    extra = copy.deepcopy(duplicate)
    extra["name"] = f"second-{duplicate_kind.value}"
    components.append(extra)

    _assert_rejected_by_schema_and_model(_validator(RELEASE_SCHEMA), ReleaseContract, payload)


@pytest.mark.parametrize("trust_level", ["L2", "L3"])
def test_public_evidence_schema_requires_boundary_for_independent_evidence(
    evidence_record_payload: dict[str, Any],
    trust_level: str,
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["trustLevel"] = trust_level
    source = payload["source"]
    assert isinstance(source, dict)
    source.pop("boundary")

    _assert_rejected_by_schema_and_model(_validator(EVIDENCE_SCHEMA), EvidenceRecord, payload)


@pytest.mark.parametrize(
    ("section", "wire_name", "python_name"),
    [
        (None, "apiVersion", "api_version"),
        ("task", "inputRef", "input_ref"),
        ("reliability", "minimumPassRate", "minimum_pass_rate"),
    ],
)
def test_public_release_contract_rejects_python_field_names(
    valid_release_contract_payload: dict[str, Any],
    section: str | None,
    wire_name: str,
    python_name: str,
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    target = payload if section is None else payload[section]
    assert isinstance(target, dict)
    target[python_name] = target.pop(wire_name)

    _assert_rejected_by_schema_and_model(_validator(RELEASE_SCHEMA), ReleaseContract, payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trials", True),
        ("trials", "20"),
        ("minimumPassRate", True),
        ("minimumPassRate", "0.95"),
    ],
)
def test_public_release_contract_rejects_scalar_coercion(
    valid_release_contract_payload: dict[str, Any], field: str, value: object
) -> None:
    payload = copy.deepcopy(valid_release_contract_payload)
    reliability = payload["reliability"]
    assert isinstance(reliability, dict)
    reliability[field] = value

    _assert_rejected_by_schema_and_model(_validator(RELEASE_SCHEMA), ReleaseContract, payload)


@pytest.mark.parametrize(
    ("section", "wire_name", "python_name"),
    [
        (None, "schemaVersion", "schema_version"),
        ("content", "sizeBytes", "size_bytes"),
        ("redaction", "policyDigest", "policy_digest"),
    ],
)
def test_public_evidence_contract_rejects_python_field_names(
    evidence_record_payload: dict[str, Any],
    section: str | None,
    wire_name: str,
    python_name: str,
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    target = payload if section is None else payload[section]
    assert isinstance(target, dict)
    target[python_name] = target.pop(wire_name)

    _assert_rejected_by_schema_and_model(_validator(EVIDENCE_SCHEMA), EvidenceRecord, payload)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("content", "sizeBytes", True),
        ("content", "sizeBytes", "4096"),
        ("redaction", "applied", 1),
        ("redaction", "applied", "true"),
    ],
)
def test_public_evidence_contract_rejects_scalar_coercion(
    evidence_record_payload: dict[str, Any], section: str, field: str, value: object
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    target = payload[section]
    assert isinstance(target, dict)
    target[field] = value

    _assert_rejected_by_schema_and_model(_validator(EVIDENCE_SCHEMA), EvidenceRecord, payload)


def test_public_evidence_schema_requires_policy_digest_when_redaction_applied(
    evidence_record_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    redaction = payload["redaction"]
    assert isinstance(redaction, dict)
    redaction.pop("policyDigest")

    _assert_rejected_by_schema_and_model(_validator(EVIDENCE_SCHEMA), EvidenceRecord, payload)
