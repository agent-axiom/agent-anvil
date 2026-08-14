from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from anvil.assurance.errors import AssuranceError
from anvil.assurance.evidence import (
    EvidenceRecord,
    EvidenceRequirement,
    TrustLevel,
    VerifiedContent,
    VerifiedEvidence,
    _create_verified_evidence,
    evidence_identity,
    match_evidence_requirement,
    match_evidence_requirements,
    validate_evidence_graph,
)


def _record(
    base_payload: dict[str, Any],
    *,
    suffix: int,
    parents: list[str] | None = None,
    evidence_type: str = "postgres.state_snapshot.v1",
    subject: str = "postgres://payments/public",
) -> EvidenceRecord:
    payload = copy.deepcopy(base_payload)
    observed_at = datetime(2026, 8, 14, 12, tzinfo=UTC) + timedelta(seconds=suffix)
    payload["observedAt"] = observed_at.isoformat().replace("+00:00", "Z")
    payload["type"] = evidence_type
    payload["subject"] = subject
    payload["parents"] = list(parents or [])
    payload["evidenceId"] = evidence_identity(payload)
    return EvidenceRecord.model_validate(payload)


def _verified(record: EvidenceRecord, trust: TrustLevel) -> VerifiedEvidence:
    return _create_verified_evidence(
        record=record,
        assigned_trust=trust,
        content=VerifiedContent(
            path=Path("/verified/content"),
            size_bytes=record.content.size_bytes,
            sha256=record.content.sha256,
        ),
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
    evidence_record_payload: dict[str, Any],
    assigned: TrustLevel,
    required: TrustLevel,
    satisfied: bool,
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    requirement = EvidenceRequirement(
        type=record.type,
        minimumTrust=required,
        subject=record.subject,
    )

    match = match_evidence_requirement(requirement, [_verified(record, assigned)])

    assert match.satisfied is satisfied
    assert match.evidence_ids == ((record.evidence_id,) if satisfied else ())


def test_requirement_matching_requires_exact_type_and_optional_subject(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    verified = _verified(record, TrustLevel.L3)
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
    evidence_record_payload: dict[str, Any],
) -> None:
    first = _record(evidence_record_payload, suffix=1)
    second = _record(evidence_record_payload, suffix=2)
    requirement = EvidenceRequirement(
        type=first.type,
        minimumTrust=TrustLevel.L2,
        subject=first.subject,
        minimumCount=2,
    )

    one_unique = match_evidence_requirement(
        requirement,
        [_verified(first, TrustLevel.L2), _verified(first, TrustLevel.L2)],
    )
    two_unique = match_evidence_requirement(
        requirement,
        [_verified(second, TrustLevel.L3), _verified(first, TrustLevel.L2)],
    )

    assert one_unique.satisfied is False
    assert one_unique.evidence_ids == (first.evidence_id,)
    assert two_unique.satisfied is True
    assert two_unique.evidence_ids == tuple(sorted([first.evidence_id, second.evidence_id]))


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
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(
        evidence_record_payload,
        suffix=1,
        parents=[f"sha256:{'f' * 64}"],
    )
    requirement = EvidenceRequirement(type=record.type, minimumTrust=TrustLevel.L0)

    with pytest.raises(AssuranceError) as captured:
        match_evidence_requirement(requirement, [_verified(record, TrustLevel.L2)])

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == "$.parents"


@pytest.mark.parametrize(
    ("field", "path"),
    [
        ("run_id", "$.runId"),
        ("release_id", "$.releaseId"),
        ("contract_id", "$.contractId"),
    ],
)
def test_requirement_matching_rejects_mixed_verified_contexts(
    evidence_record_payload: dict[str, Any], field: str, path: str
) -> None:
    first = _record(evidence_record_payload, suffix=1)
    second = _record(evidence_record_payload, suffix=2)
    changed = second.model_copy(update={field: f"different-{field}"})
    requirement = EvidenceRequirement(type=first.type, minimumTrust=TrustLevel.L0)

    with pytest.raises(AssuranceError) as captured:
        match_evidence_requirement(
            requirement,
            [_verified(first, TrustLevel.L2), _verified(changed, TrustLevel.L2)],
        )

    assert captured.value.code == "evidence_schema_error"
    assert captured.value.path == path


def test_match_evidence_requirements_preserves_requirement_order(
    evidence_record_payload: dict[str, Any],
) -> None:
    record = _record(evidence_record_payload, suffix=1)
    requirements = [
        EvidenceRequirement(type="agent.trace.v1", minimumTrust=TrustLevel.L1),
        EvidenceRequirement(type=record.type, minimumTrust=TrustLevel.L2),
    ]

    matches = match_evidence_requirements(requirements, [_verified(record, TrustLevel.L2)])

    assert [match.requirement.type for match in matches] == [
        "agent.trace.v1",
        record.type,
    ]
    assert [match.satisfied for match in matches] == [False, True]
