from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from anvil.assurance.canonical import sha256_bytes
from anvil.assurance.errors import AssuranceError
from anvil.assurance.evidence import (
    EVIDENCE_RECORD_SCHEMA_VERSION,
    MAX_EVIDENCE_CONTENT_BYTES,
    EvidenceRecord,
    EvidenceTrustPolicy,
    ObservedEvidenceSource,
    TrustAssignment,
    TrustLevel,
    VerifiedContent,
    VerifiedEvidence,
    evidence_identity,
    verify_evidence_content,
    verify_evidence_identity,
    verify_evidence_record,
    verify_evidence_trust,
)


def _record(payload: dict[str, Any]) -> EvidenceRecord:
    return EvidenceRecord.model_validate(payload)


def _reidentify(payload: dict[str, Any]) -> dict[str, Any]:
    payload["evidenceId"] = evidence_identity(payload)
    return payload


def _content_record(
    evidence_record_payload: dict[str, Any],
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


def observed_source() -> ObservedEvidenceSource:
    return ObservedEvidenceSource(
        collector="postgres-observer",
        version="0.1.0",
        boundary="separate-read-only-credentials",
    )


def test_evidence_record_round_trips_aliases_and_identity(
    evidence_record_payload: dict[str, Any],
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
    evidence_record_payload: dict[str, Any],
) -> None:
    reversed_payload = dict(reversed(list(evidence_record_payload.items())))

    assert evidence_identity(reversed_payload) == evidence_record_payload["evidenceId"]


def test_evidence_identity_normalizes_mapping_and_model_timestamps_identically(
    evidence_record_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["observedAt"] = "2026-08-14T12:00:00+00:00"
    payload["evidenceId"] = evidence_identity(payload)
    record = EvidenceRecord.model_validate(payload)

    assert evidence_identity(payload) == evidence_identity(record)


def test_evidence_identity_canonicalizes_parent_edge_order(
    evidence_record_payload: dict[str, Any],
) -> None:
    first = copy.deepcopy(evidence_record_payload)
    second = copy.deepcopy(evidence_record_payload)
    first["parents"] = [f"sha256:{'1' * 64}", f"sha256:{'2' * 64}"]
    second["parents"] = list(reversed(first["parents"]))

    assert evidence_identity(first) == evidence_identity(second)


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
    evidence_record_payload: dict[str, Any], field: str
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
    evidence_record_payload: dict[str, Any], section: str | None, field: str
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
    evidence_record_payload: dict[str, Any], path: tuple[str, ...], value: object
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
    evidence_record_payload: dict[str, Any], path: tuple[str, ...], value: object
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
    evidence_record_payload: dict[str, Any],
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


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "x-api-key",
        "authorization",
        "password",
        "client_secret",
        "secret",
        "token",
        "accessToken",
        "jwt",
        "private-key",
    ],
)
def test_evidence_record_rejects_secret_like_correlation_keys(
    evidence_record_payload: dict[str, Any], key: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    correlations = payload["correlations"]
    assert isinstance(correlations, dict)
    correlations[key] = "must-not-persist"

    with pytest.raises(ValidationError, match="secret-like correlation keys") as captured:
        _record(payload)

    assert "must-not-persist" not in str(captured.value)


def test_evidence_identity_hides_invalid_mapping_input(
    evidence_record_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload.pop("evidenceId")
    payload["subject"] = {"api_key": "must-not-persist"}

    with pytest.raises(ValidationError) as captured:
        evidence_identity(payload)

    assert "must-not-persist" not in str(captured.value)


@pytest.mark.parametrize("trust_level", ["L2", "L3"])
def test_independent_evidence_requires_boundary(
    evidence_record_payload: dict[str, Any], trust_level: str
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
    evidence_record_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    redaction = payload["redaction"]
    assert isinstance(redaction, dict)
    redaction["policyDigest"] = None

    with pytest.raises(ValidationError, match="policyDigest is required"):
        _record(payload)


def test_trust_policy_verifies_exact_source_assignment(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload)

    verified = verify_evidence_trust(
        record,
        trust_policy(),
        observed_source=observed_source(),
    )

    assert verified.record is record
    assert verified.assigned_trust is TrustLevel.L2


@pytest.mark.parametrize("claimed", [TrustLevel.L0, TrustLevel.L1, TrustLevel.L2])
def test_trust_policy_accepts_claim_at_or_below_assignment(
    evidence_record_payload: dict[str, Any], claimed: TrustLevel
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["trustLevel"] = claimed.value
    _reidentify(payload)
    record = _record(payload)

    verified = verify_evidence_trust(
        record,
        trust_policy(TrustLevel.L2),
        observed_source=observed_source(),
    )

    assert verified.assigned_trust is claimed


def test_record_cannot_self_elevate_claimed_trust(
    evidence_record_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["trustLevel"] = "L3"
    _reidentify(payload)
    record = _record(payload)

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_trust(
            record,
            trust_policy(TrustLevel.L2),
            observed_source=observed_source(),
        )

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
    evidence_record_payload: dict[str, Any], field: str, value: str
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    source = payload["source"]
    assert isinstance(source, dict)
    source[field] = value
    _reidentify(payload)
    record = _record(payload)

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_trust(
            record,
            trust_policy(),
            observed_source=observed_source(),
        )

    assert captured.value.code == "evidence_trust_error"
    assert captured.value.path == "$.source"


def test_trust_policy_rejects_producer_source_not_observed_by_ingestion(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload)
    untrusted_observation = ObservedEvidenceSource(
        collector="untrusted-upload",
        version="1.0.0",
        boundary=None,
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_trust(
            record,
            trust_policy(),
            observed_source=untrusted_observation,
        )

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
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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
    evidence_record_payload: dict[str, Any],
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
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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


def test_verify_evidence_content_rejects_final_component_symlink_swap(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    target = store / "snapshot.json"
    target.write_bytes(b"original")
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside secret")
    record = _content_record(
        evidence_record_payload,
        relative_path="snapshot.json",
        content=outside.read_bytes(),
    )
    original_is_file = Path.is_file
    swapped = False

    def swap_after_containment_check(path: Path) -> bool:
        nonlocal swapped
        if path == target.resolve() and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(outside)
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", swap_after_containment_check)

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, store)

    assert swapped is True
    assert captured.value.code == "evidence_path_escape"
    assert "outside secret" not in str(captured.value)


def test_verify_evidence_content_rejects_directory_target(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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


def test_verify_evidence_content_rejects_oversized_declaration_before_path_access(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    content = payload["content"]
    assert isinstance(content, dict)
    content["path"] = "missing.json"
    content["sizeBytes"] = MAX_EVIDENCE_CONTENT_BYTES + 1
    record = _record(_reidentify(payload))

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_content(record, tmp_path)

    assert captured.value.code == "evidence_content_too_large"
    assert captured.value.path == "$.content.sizeBytes"


def test_verify_evidence_content_rejects_wrong_digest(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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
        expected_run_id=record.run_id,
        expected_release_id=record.release_id,
        expected_contract_id=record.contract_id,
        observed_source=observed_source(),
        trust_policy=trust_policy(),
        store_root=tmp_path,
    )

    assert verified.record == record
    assert verified.record is not record
    assert verified.evidence_id == record.evidence_id
    assert verified.run_id == record.run_id
    assert verified.assigned_trust is TrustLevel.L2
    assert verified.content.path == (tmp_path / "evidence.json").resolve()


def test_verified_evidence_cannot_be_constructed_without_verifier(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload)

    with pytest.raises(TypeError):
        cast(Any, VerifiedEvidence)(
            record=record,
            assigned_trust=TrustLevel.L3,
            content=VerifiedContent(
                path=Path("missing"),
                size_bytes=0,
                sha256="0" * 64,
            ),
        )
    with pytest.raises(TypeError):
        cast(Any, VerifiedEvidence)()


def test_verified_evidence_is_immutable_after_original_record_mutation(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
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
        expected_run_id=record.run_id,
        expected_release_id=record.release_id,
        expected_contract_id=record.contract_id,
        observed_source=observed_source(),
        trust_policy=trust_policy(),
        store_root=tmp_path,
    )

    record.type = "agent.trace.v1"
    record.parents.append(f"sha256:{'f' * 64}")

    assert verified.type == "postgres.state_snapshot.v1"
    assert verified.parents == ()
    assert verified.record.type == "postgres.state_snapshot.v1"


def test_verify_evidence_record_rejects_wrong_release_before_content_read(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
) -> None:
    record = _content_record(
        evidence_record_payload,
        relative_path="missing.json",
        content=b"missing",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_record(
            record,
            expected_run_id=record.run_id,
            expected_release_id=f"sha256:{'0' * 64}",
            expected_contract_id=record.contract_id,
            observed_source=observed_source(),
            trust_policy=trust_policy(),
            store_root=tmp_path,
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.releaseId"


def test_verify_evidence_record_rejects_cross_contract_replay_before_content_read(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
) -> None:
    record = _content_record(
        evidence_record_payload,
        relative_path="missing.json",
        content=b"missing",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_record(
            record,
            expected_run_id=record.run_id,
            expected_release_id=record.release_id,
            expected_contract_id="different-contract",
            observed_source=observed_source(),
            trust_policy=trust_policy(),
            store_root=tmp_path,
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.contractId"


def test_verify_evidence_record_rejects_cross_run_replay_before_content_read(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
) -> None:
    record = _content_record(
        evidence_record_payload,
        relative_path="missing.json",
        content=b"missing",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_record(
            record,
            expected_run_id="different-run",
            expected_release_id=record.release_id,
            expected_contract_id=record.contract_id,
            observed_source=observed_source(),
            trust_policy=trust_policy(),
            store_root=tmp_path,
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.runId"


def test_verify_evidence_record_normalizes_unicode_contract_mismatch(
    tmp_path: Path, evidence_record_payload: dict[str, Any]
) -> None:
    payload = copy.deepcopy(evidence_record_payload)
    payload["contractId"] = "контракт"
    record = _content_record(
        payload,
        relative_path="missing.json",
        content=b"missing",
    )

    with pytest.raises(AssuranceError) as captured:
        verify_evidence_record(
            record,
            expected_run_id=record.run_id,
            expected_release_id=record.release_id,
            expected_contract_id="different-contract",
            observed_source=observed_source(),
            trust_policy=trust_policy(),
            store_root=tmp_path,
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.contractId"


@pytest.mark.skipif(os.name != "posix", reason="descriptor flags are POSIX-specific")
def test_verify_evidence_content_opens_final_component_nonblocking(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"verified"
    (tmp_path / "evidence.json").write_bytes(content)
    record = _content_record(
        evidence_record_payload,
        relative_path="evidence.json",
        content=content,
    )
    original_open = os.open
    inspected = False

    def inspect_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal inspected
        if path == "evidence.json":
            inspected = True
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", inspect_open)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, inspect_open})

    verify_evidence_content(record, tmp_path)

    assert inspected is True
