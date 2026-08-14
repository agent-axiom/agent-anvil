from __future__ import annotations

import math

import pytest

from anvil.assurance.canonical import canonical_json_bytes, sha256_bytes, sha256_json


def test_canonical_json_is_utf8_sorted_and_compact() -> None:
    assert canonical_json_bytes({"z": "Привет", "a": [2, 1]}) == (
        '{"a":[2,1],"z":"Привет"}'.encode()
    )


def test_canonical_json_preserves_array_order() -> None:
    assert canonical_json_bytes({"items": [3, 1, 2]}) == b'{"items":[3,1,2]}'


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {1, 2}])
def test_canonical_json_rejects_non_json_values(value: object) -> None:
    with pytest.raises(ValueError, match="value is not canonical JSON"):
        canonical_json_bytes(value)


def test_sha256_bytes_supports_prefixed_and_raw_digests() -> None:
    expected = "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"

    assert sha256_bytes(b'{"a":1}') == f"sha256:{expected}"
    assert sha256_bytes(b'{"a":1}', prefix=False) == expected


def test_sha256_json_has_prefixed_lowercase_digest() -> None:
    assert sha256_json({"a": 1}) == (
        "sha256:015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"
    )
