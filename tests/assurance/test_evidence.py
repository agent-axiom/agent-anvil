from __future__ import annotations

import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from anvil.assurance.canonical import sha256_bytes
from anvil.assurance.errors import AssuranceError
from anvil.assurance.evidence import (
    EVIDENCE_RECORD_SCHEMA_VERSION,
    EvidenceRecord,
    EvidenceTrustPolicy,
    TrustAssignment,
    TrustLevel,
    evidence_identity,
    verify_evidence_content,
    verify_evidence_identity,
    verify_evidence_record,
    verify_evidence_trust,
)


def _record(payload: dict[str, object]) -> EvidenceRecord:
    return EvidenceRecord.model_validate(payload)


def _reidentify(payload: dict[str, object]) -> dict[str, object]:
    payload["evidenceId"] = evidence_identity(payload)
    return payload


def _content_record(
    evidence_record_payload: dict[str, object],
    *,
    relative_path: str,
    content: bytes,
) -> EvidenceRecord:
    payload = copy.deepcopy(evidence_record_payload)
    content_payload = payload["content"]
    assert isinstance(content_payload, dict)
    content_payload.update(
        {
            "path": relative_path,
            "sizeBytes": len(content),
            "sha256": sha256_bytes(content, prefix=False),
        }
    )
    return _record(_reidentify(payload))


def trust_policy(maximum_trust: TrustLevel = TrustLevel.L2) -> EvidenceTrustPolicy:
    return EvidenceTrustPolicy(
        assignments=[
            TrustAssignment(
                collector="postgres-observer",
                version="0.1.0",
                boundary="separate-read-only-credentials",
                maximum_trust=maximum_trust,
            )
        ]
    )


def test_evidence_record_round_trips_aliases_and_identity(
    evidence_record_payload: dict[str, object],
) -> None:
    record = _record(evidence_record_payload)

    assert record.schema_version == EVIDENCE_RECORD_SCHEMA_VERSION
    assert record.trust_level is TrustLevel.L2
    assert record.content.media_type == "application/json"
    assert record.content.size_bytes == 4096
    assert record.redaction.policy_digest == f"sha256:{'9' * 64}"
    assert verify_evidence_identity(record) is None
    dumped = record.model_dump(mode="json", by_alias=True)
    assert dumped["schemaVersion"] == EVIDENCE_RECORD_SCHEMA_VERSION
    assert dumped["evidenceId"] == evidence_record_payload["evidenceId"]
    assert dumped["trustLevel"] == "L2"
    assert dumped["content"]["sizeBytes"] == 4096


def test_evidence_identity_is_independent_of_mapping_order(
    evidence_record_payload: dict[str, object],
) -> None:
    reversed_payload = dict(reversed(list(evidence_record_payload.items())))

    assert evidence_identity(reversed_payload) == evidence_record_payload["evidenceId"]


@pytest.mark.parametrize(
    "field",
    [
        "schemaVersion",
        "evidenceId",
        "runId",
        "releaseId",
        "contractId",
        "type",
        "trustLevel",
        "subject",
        "source",
        "observedAt",
        "content",
        "redaction",
    ],
)
def test_evidence_record_rejects_missing_required_fields(
    evidence_record_payload: dict[str, object], field: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    del payload[field]

    with pytest.raises(ValidationError, match="Field required"):
        _record(payload)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        (None, "unexpected"),
        ("source", "credentials"),
        ("content", "inline"),
        ("redaction", "reason"),
    ],
)
def test_evidence_record_rejects_unknown_fields(
    evidence_record_payload: dict[str, object], section: str | None, field: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    target = payload if section is None else payload[section]
    assert isinstance(target, dict)
    target[field] = "not-allowed"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _record(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("evidenceId",), "8" * 64),
        (("releaseId",), f"sha256:{'A' * 64}"),
        (("type",), "state_snapshot"),
        (("observedAt",), "2026-08-14T12:00:00"),
        (("content", "sha256"), f"sha256:{'8' * 64}"),
        (("content", "sizeBytes"), -1),
    ],
)
def test_evidence_record_rejects_invalid_shape(
    evidence_record_payload: dict[str, object], path: tuple[str, ...], value: object
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    target = payload
    for part in path[:-1]:
        nested = target[part]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        _record(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("runId",), "assure_changed"),
        (("releaseId",), f"sha256:{'6' * 64}"),
        (("contractId",), "changed-contract"),
        (("type",), "postgres.transaction_log.v1"),
        (("trustLevel",), "L1"),
        (("subject",), "postgres://payments/other"),
        (("observedAt",), "2026-08-14T12:00:01Z"),
        (("source", "version"), "0.1.1"),
        (("content", "sha256"), "a" * 64),
        (("correlations", "transactionId"), "735129"),
        (("redaction", "policyDigest"), f"sha256:{'a' * 64}"),
    ],
)
def test_evidence_identity_binds_all_record_metadata(
    evidence_record_payload: dict[str, object], path: tuple[str, ...], value: object
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    target = payload
    for part in path[:-1]:
        nested = target[part]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value
    record = _record(payload)

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_identity(record)

    assert captured.value.code == "evidence_digest_mismatch"
    assert captured.value.path == "$.evidenceId"


def test_evidence_record_rejects_duplicate_or_self_parents(
    evidence_record_payload: dict[str, object],
) -> None:
    parent = f"sha256:{'a' * 64}"
    duplicate_payload = copy.deepcopy(evidence_record_payload)
    duplicate_payload["parents"] = [parent, parent]
    self_payload = copy.deepcopy(evidence_record_payload)
    self_payload["parents"] = [self_payload["evidenceId"]]

    with pytest.raises(ValidationError, match="duplicate parent"):
        _record(duplicate_payload)
    with pytest.raises(ValidationError, match="cannot reference itself"):
        _record(self_payload)


@pytest.mark.parametrize("key", ["api_key", "authorization", "password", "secret", "token"])
def test_evidence_record_rejects_secret_like_correlation_keys(
    evidence_record_payload: dict[str, object], key: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    correlations = payload["correlations"]
    assert isinstance(correlations, dict)
    correlations[key] = "must-not-persist"

    with pytest.raises(ValidationError, match="secret-like correlation keys"):
        _record(payload)


@pytest.mark.parametrize("trust_level", ["L2", "L3"])
def test_independent_evidence_requires_boundary(
    evidence_record_payload: dict[str, object], trust_level: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["trustLevel"] = trust_level
    source = payload["source"]
    assert isinstance(source, dict)
    source["boundary"] = None
    _reidentify(payload)

    with pytest.raises(ValidationError, match="L2 and L3 evidence require"):
        _record(payload)


def test_applied_redaction_requires_policy_digest(
    evidence_record_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    redaction = payload["redaction"]
    assert isinstance(redaction, dict)
    redaction["policyDigest"] = None

    with pytest.raises(ValidationError, match="policyDigest is required"):
        _record(payload)


def test_trust_policy_verifies_exact_source_assignment(
    evidence_record_payload: dict[str, object],
) -> None:
    record = _record(evidence_record_payload)

    verified = verify_evidence_trust(record, trust_policy())

    assert verified.record is record
    assert verified.assigned_trust is TrustLevel.L2


@pytest.mark.parametrize("claimed", [TrustLevel.L0, TrustLevel.L1, TrustLevel.L2])
def test_trust_policy_accepts_claim_at_or_below_assignment(
    evidence_record_payload: dict[str, object], claimed: TrustLevel
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["trustLevel"] = claimed.value
    _reidentify(payload)
    record = _record(payload)

    verified = verify_evidence_trust(record, trust_policy(TrustLevel.L2))

    assert verified.assigned_trust is claimed


def test_record_cannot_self_elevate_claimed_trust(
    evidence_record_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["trustLevel"] = "L3"
    _reidentify(payload)
    record = _record(payload)

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_trust(record, trust_policy(TrustLevel.L2))

    assert captured.value.code == "evidence_trust_error"
    assert captured.value.path == "$.trustLevel"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("collector", "different-observer"),
        ("version", "0.2.0"),
        ("boundary", "shared-agent-credentials"),
    ],
)
def test_trust_policy_rejects_unassigned_source(
    evidence_record_payload: dict[str, object], field: str, value: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    source = payload["source"]
    assert isinstance(source, dict)
    source[field] = value
    _reidentify(payload)
    record = _record(payload)

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_trust(record, trust_policy())

    assert captured.value.code == "evidence_trust_error"
    assert captured.value.path == "$.source"


def test_trust_policy_rejects_duplicate_assignments() -> None:
    assignment = TrustAssignment(
        collector="observer",
        version="1.0.0",
        boundary="separate",
        maximum_trust=TrustLevel.L2,
    )

    with pytest.raises(ValidationError, match="duplicate trust assignments"):
        EvidenceTrustPolicy(assignments=[assignment, assignment.model_copy()])


def test_verify_evidence_content_accepts_contained_regular_file(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    content = b'{"refunds":[{"order_id":42}]}'
    content_path = tmp_path / "objects" / "81" / "snapshot.json"
    content_path.parent.mkdir(parents=True)
    content_path.write_bytes(content)
    record = _content_record(
        evidence_record_payload,
        relative_path="objects/81/snapshot.json",
        content=content,
    )

    verified = verify_evidence_content(record, tmp_path)

    assert verified.path == content_path.resolve()
    assert verified.size_bytes == len(content)
    assert verified.sha256 == sha256_bytes(content, prefix=False)


def test_verify_evidence_content_rejects_missing_file(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    record = _content_record(
        evidence_record_payload,
        relative_path="objects/missing.json",
        content=b"missing",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, tmp_path)

    assert captured.value.code == "evidence_content_missing"
    assert captured.value.path == "$.content.path"


@pytest.mark.parametrize(
    "relative_path",
    [
        "/tmp/outside.json",
        "../outside.json",
        "objects/../outside.json",
        "objects/./snapshot.json",
        "objects//snapshot.json",
        "objects\\snapshot.json",
    ],
)
def test_verify_evidence_content_rejects_non_normalized_or_escaping_paths(
    tmp_path: Path,
    evidence_record_payload: dict[str, object],
    relative_path: str,
) -> None:
    record = _content_record(
        evidence_record_payload,
        relative_path=relative_path,
        content=b"content",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, tmp_path)

    assert captured.value.code == "evidence_path_escape"
    assert captured.value.path == "$.content.path"


def test_verify_evidence_content_rejects_symlink_escape(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside secret")
    link = store / "snapshot.json"
    link.symlink_to(outside)
    record = _content_record(
        evidence_record_payload,
        relative_path="snapshot.json",
        content=outside.read_bytes(),
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, store)

    assert captured.value.code == "evidence_path_escape"
    assert "outside secret" not in str(captured.value)


def test_verify_evidence_content_rejects_directory_target(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    directory = tmp_path / "objects"
    directory.mkdir()
    record = _content_record(
        evidence_record_payload,
        relative_path="objects",
        content=b"",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, tmp_path)

    assert captured.value.code == "evidence_content_missing"
    assert captured.value.path == "$.content.path"


def test_verify_evidence_content_rejects_wrong_size(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    content_path = tmp_path / "snapshot.json"
    content_path.write_bytes(b"actual")
    record = _content_record(
        evidence_record_payload,
        relative_path="snapshot.json",
        content=b"different-size",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, tmp_path)

    assert captured.value.code == "evidence_digest_mismatch"
    assert captured.value.path == "$.content.sizeBytes"


def test_verify_evidence_content_rejects_wrong_digest(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    content_path = tmp_path / "snapshot.json"
    content_path.write_bytes(b"actual")
    record = _content_record(
        evidence_record_payload,
        relative_path="snapshot.json",
        content=b"xxxxxx",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, tmp_path)

    assert captured.value.code == "evidence_digest_mismatch"
    assert captured.value.path == "$.content.sha256"


def test_verify_evidence_record_composes_identity_release_trust_and_content(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    content = b"verified"
    (tmp_path / "evidence.json").write_bytes(content)
    record = _content_record(
        evidence_record_payload,
        relative_path="evidence.json",
        content=content,
    )

    verified = verify_evidence_record(
        record,
        expected_release_id=record.release_id,
        trust_policy=trust_policy(),
        store_root=tmp_path,
    )

    assert verified.record is record
    assert verified.assigned_trust is TrustLevel.L2
    assert verified.content.path == (tmp_path / "evidence.json").resolve()


def test_verify_evidence_record_rejects_wrong_release_before_content_read(
    tmp_path: Path, evidence_record_payload: dict[str, object]
) -> None:
    record = _content_record(
        evidence_record_payload,
        relative_path="missing.json",
        content=b"missing",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_record(
            record,
            expected_release_id=f"sha256:{'0' * 64}",
            trust_policy=trust_policy(),
            store_root=tmp_path,
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.releaseId"
