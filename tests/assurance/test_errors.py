from __future__ import annotations

import pytest

from anvil.assurance.errors import AssuranceError


def test_assurance_error_exposes_stable_code_path_and_details() -> None:
    error = AssuranceError(
        "component is missing",
        code="release_identity_incomplete",
        path="$.release.components",
        details={"missing": ["policy"]},
    )

    assert error.code == "release_identity_incomplete"
    assert error.path == "$.release.components"
    assert error.details == {"missing": ["policy"]}
    assert str(error) == (
        "release_identity_incomplete at $.release.components: component is missing"
    )


@pytest.mark.parametrize(
    "secret_key",
    ["api_key", "API_KEY", "authorization", "password", "secret", "token"],
)
def test_assurance_error_rejects_secret_details(secret_key: str) -> None:
    with pytest.raises(ValueError, match="details must not contain secret-like keys"):
        AssuranceError(
            "invalid source",
            code="evidence_trust_error",
            path="$.source",
            details={secret_key: "must-not-leak"},
        )
