from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from anvil.assurance.canonical import sha256_bytes
from anvil.assurance.errors import AssuranceError
from anvil.assurance.evidence import (
    EvidenceRecord,
    EvidenceRequirement,
    EvidenceTrustPolicy,
    ObservedEvidenceSource,
    TrustAssignment,
    TrustLevel,
    VerifiedEvidence,
    evidence_identity,
    match_evidence_requirement,
    match_evidence_requirements,
    validate_evidence_graph,
    verify_evidence_record,
)


def _record(
    base_payload: dict[str, Any],
    *,
    suffix: int,
    parents: list[str] | None = None,
    evidence_type: str = "postgres.state_snapshot.v1",
    subject: str = "postgres://payments/public",
    trust_level: TrustLevel = TrustLevel.L2,
    run_id: str | None = None,
    release_id: str | None = None,
    contract_id: str | None = None,
) -> EvidenceRecord:
    payload = copy.deepcopy(base_payload)
    observed_at = datetime(2026, 8, 14, 12, tzinfo=UTC) + timedelta(seconds=suffix)
    content = f"evidence-{suffix}".encode()
    payload["observedAt"] = observed_at.isoformat().replace("+00:00", "Z")
    payload["type"] = evidence_type
    payload["subject"] = subject
    payload["trustLevel"] = trust_level.value
    payload["runId"] = run_id or payload["runId"]
    payload["releaseId"] = release_id or payload["releaseId"]
    payload["contractId"] = contract_id or payload["contractId"]
    payload["content"] = {
        "mediaType": "application/json",
        "sha256": sha256_bytes(content, prefix=False),
        "sizeBytes": len(content),
        "path": f"evidence-{suffix}.json",
    }
    payload["parents"] = list(parents or [])
    payload["evidenceId"] = evidence_identity(payload)
    return EvidenceRecord.model_validate(payload)


def _verified(record: EvidenceRecord, store_root: Path) -> VerifiedEvidence:
    content_path = store_root / record.content.path
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_bytes(content_path.stem.encode())
    observed_source = ObservedEvidenceSource(
        collector=record.source.collector,
        version=record.source.version,
        boundary=record.source.boundary,
    )
    trust_policy = EvidenceTrustPolicy(
        assignments=[
            TrustAssignment(
                collector=record.source.collector,
                version=record.source.version,
                boundary=record.source.boundary,
                maximum_trust=TrustLevel.L3,
            )
        ]
    )
    return verify_evidence_record(
        record,
        expected_run_id=record.run_id,
        expected_release_id=record.release_id,
        expected_contract_id=record.contract_id,
        observed_source=observed_source,
        trust_policy=trust_policy,
        store_root=store_root,
    )


def test_validate_evidence_graph_returns_deterministic_topological_order(
    evidence_record_payload: dict[str, Any],
) -> None:
    pre_state = _record(evidence_record_payload, suffix=1)
    trace = _record(
        evidence_record_payload,
        suffix=2,
        parents=[pre_state.evidence_id],
        evidence_type="agent.trace.v1",
        subject="agent://refund-agent",
    )
    post_state = _record(
        evidence_record_payload,
        suffix=3,
        parents=[trace.evidence_id],
    )

    ordered = validate_evidence_graph([post_state, trace, pre_state])

    assert [record.evidence_id for record in ordered] == [
        pre_state.evidence_id,
        trace.evidence_id,
        post_state.evidence_id,
    ]


def test_validate_evidence_graph_is_independent_of_input_order(
    evidence_record_payload: dict[str, Any],
) -> None:
    first = _record(evidence_record_payload, suffix=1)
    second = _record(evidence_record_payload, suffix=2)

    forward = validate_evidence_graph([first, second])
    reverse = validate_evidence_graph([second, first])

    assert [record.evidence_id for record in forward] == [record.evidence_id for record in reverse]


def test_validate_evidence_graph_rejects_duplicate_record_ids(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)

    with pytest.raises(AssuranceError) as captured:
        validate_evidence_graph([record, record.model_copy()])

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.evidenceId"


def test_validate_evidence_graph_rejects_duplicate_parents_even_for_unvalidated_copy(
    evidence_record_payload: dict[str, Any],
) -> None:
    parent = _record(evidence_record_payload, suffix=1)
    child = _record(evidence_record_payload, suffix=2, parents=[parent.evidence_id])
    invalid = child.model_copy(update={"parents": [parent.evidence_id, parent.evidence_id]})

    with pytest.raises(AssuranceError) as captured:
        validate_evidence_graph([parent, invalid])

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.parents"


def test_validate_evidence_graph_rejects_self_parent_even_for_unvalidated_copy(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    invalid = record.model_copy(update={"parents": [record.evidence_id]})

    with pytest.raises(AssuranceError) as captured:
        validate_evidence_graph([invalid])

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.parents"


def test_validate_evidence_graph_rejects_dangling_parent(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(
        evidence_record_payload,
        suffix=1,
        parents=[f"sha256:{'f' * 64}"],
    )

    with pytest.raises(AssuranceError) as captured:
        validate_evidence_graph([record])

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.parents"


def test_validate_evidence_graph_rejects_cycle_without_recursion(
    evidence_record_payload: dict[str, Any],
) -> None:
    first = _record(evidence_record_payload, suffix=1)
    second = _record(evidence_record_payload, suffix=2)
    first_in_cycle = first.model_copy(update={"parents": [second.evidence_id]})
    second_in_cycle = second.model_copy(update={"parents": [first.evidence_id]})

    with pytest.raises(AssuranceError) as captured:
        validate_evidence_graph([first_in_cycle, second_in_cycle])

    assert captured.value.code == "evidence_graph_cycle"
    assert captured.value.path == "$.parents"


@pytest.mark.parametrize(
    ("assigned", "required", "satisfied"),
    [
        (assigned, required, assigned.rank >= required.rank)
        for assigned in TrustLevel
        for required in TrustLevel
    ],
)
def test_requirement_matching_uses_monotonic_trust(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
    assigned: TrustLevel,
    required: TrustLevel,
    satisfied: bool,
) -> None:
    record = _record(evidence_record_payload, suffix=1, trust_level=assigned)
    requirement = EvidenceRequirement(
        type=record.type,
        minimumTrust=required,
        subject=record.subject,
    )

    match = match_evidence_requirement(requirement, [_verified(record, tmp_path)])

    assert match.satisfied is satisfied
    assert match.evidence_ids == ((record.evidence_id,) if satisfied else ())


def test_requirement_matching_requires_exact_type_and_optional_subject(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1, trust_level=TrustLevel.L3)
    verified = _verified(record, tmp_path)
    matching = EvidenceRequirement(
        type="postgres.state_snapshot.v1",
        minimumTrust=TrustLevel.L2,
    )
    wrong_type = matching.model_copy(update={"type": "agent.trace.v1"})
    wrong_subject = matching.model_copy(update={"subject": "postgres://other"})

    assert match_evidence_requirement(matching, [verified]).satisfied is True
    assert match_evidence_requirement(wrong_type, [verified]).satisfied is False
    assert match_evidence_requirement(wrong_subject, [verified]).satisfied is False


def test_requirement_matching_enforces_minimum_count_and_deduplicates_ids(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
) -> None:
    first = _record(evidence_record_payload, suffix=1)
    second = _record(evidence_record_payload, suffix=2, trust_level=TrustLevel.L3)
    requirement = EvidenceRequirement(
        type=first.type,
        minimumTrust=TrustLevel.L2,
        subject=first.subject,
        minimumCount=2,
    )

    one_unique = match_evidence_requirement(
        requirement,
        [_verified(first, tmp_path), _verified(first, tmp_path)],
    )
    two_unique = match_evidence_requirement(
        requirement,
        [_verified(second, tmp_path), _verified(first, tmp_path)],
    )

    assert one_unique.satisfied is False
    assert one_unique.evidence_ids == (first.evidence_id,)
    assert two_unique.satisfied is True
    assert two_unique.evidence_ids == tuple(sorted([first.evidence_id, second.evidence_id]))


def test_requirement_matching_deduplicates_canonically_equivalent_records(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
) -> None:
    first_parent = _record(evidence_record_payload, suffix=1)
    second_parent = _record(evidence_record_payload, suffix=2)
    child = _record(
        evidence_record_payload,
        suffix=3,
        parents=[first_parent.evidence_id, second_parent.evidence_id],
        evidence_type="agent.trace.v1",
        subject="agent://refund-agent",
    )
    payload = child.model_dump(mode="json", by_alias=True)
    payload["parents"] = list(reversed(payload["parents"]))
    correlations = payload["correlations"]
    assert isinstance(correlations, dict)
    payload["correlations"] = dict(reversed(list(correlations.items())))
    reordered = EvidenceRecord.model_validate(payload)
    requirement = EvidenceRequirement(
        type=child.type,
        minimumTrust=TrustLevel.L1,
        subject=child.subject,
    )

    match = match_evidence_requirement(
        requirement,
        [
            _verified(child, tmp_path),
            _verified(first_parent, tmp_path),
            _verified(reordered, tmp_path),
            _verified(second_parent, tmp_path),
        ],
    )

    assert reordered.evidence_id == child.evidence_id
    assert match.satisfied is True
    assert match.evidence_ids == (child.evidence_id,)


def test_requirement_matching_rejects_raw_unverified_record(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    requirement = EvidenceRequirement(type=record.type, minimumTrust=TrustLevel.L0)

    with pytest.raises(TypeError, match="VerifiedEvidence"):
        match_evidence_requirement(requirement, cast(Any, [record]))


def test_requirement_matching_rejects_unsealed_verified_marker(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    requirement = EvidenceRequirement(type=record.type, minimumTrust=TrustLevel.L0)
    forged = object.__new__(VerifiedEvidence)

    with pytest.raises(TypeError, match="verified by verify_evidence_record"):
        match_evidence_requirement(requirement, cast(Any, [forged]))


def test_requirement_matching_rejects_dangling_verified_graph(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(
        evidence_record_payload,
        suffix=1,
        parents=[f"sha256:{'f' * 64}"],
    )
    requirement = EvidenceRequirement(type=record.type, minimumTrust=TrustLevel.L0)

    with pytest.raises(AssuranceError) as captured:
        match_evidence_requirement(requirement, [_verified(record, tmp_path)])

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.parents"


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("run_id", "different-run", "$.runId"),
        ("release_id", f"sha256:{'6' * 64}", "$.releaseId"),
        ("contract_id", "different-contract", "$.contractId"),
    ],
)
def test_requirement_matching_rejects_mixed_verified_contexts(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
    field: str,
    value: str,
    path: str,
) -> None:
    first = _record(evidence_record_payload, suffix=1)
    context = {
        "run_id": first.run_id,
        "release_id": first.release_id,
        "contract_id": first.contract_id,
    }
    context[field] = value
    changed = _record(
        evidence_record_payload,
        suffix=2,
        run_id=context["run_id"],
        release_id=context["release_id"],
        contract_id=context["contract_id"],
    )
    requirement = EvidenceRequirement(type=first.type, minimumTrust=TrustLevel.L0)

    with pytest.raises(AssuranceError) as captured:
        match_evidence_requirement(
            requirement,
            [_verified(first, tmp_path), _verified(changed, tmp_path)],
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == path


def test_match_evidence_requirements_preserves_requirement_order(
    tmp_path: Path,
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    requirements = [
        EvidenceRequirement(type="agent.trace.v1", minimumTrust=TrustLevel.L1),
        EvidenceRequirement(type=record.type, minimumTrust=TrustLevel.L2),
    ]

    matches = match_evidence_requirements(requirements, [_verified(record, tmp_path)])

    assert [match.requirement.type for match in matches] == [
        "agent.trace.v1",
        record.type,
    ]
    assert [match.satisfied for match in matches] == [False, True]
