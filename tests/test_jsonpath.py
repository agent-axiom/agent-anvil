from __future__ import annotations

import pytest

from anvil.jsonpath import is_supported_json_path, json_path_get


@pytest.mark.parametrize(
    "path",
    ["$", "$.order_id", "$.customer.profile.id", "$.orders[0].order_id", "$[0].id"],
)
def test_is_supported_json_path_accepts_stable_subset(path: str) -> None:
    assert is_supported_json_path(path)


@pytest.mark.parametrize(
    "path",
    ["order_id", "$.", "$..order_id", "$.orders[*].id", "$.orders[-1].id", "$.orders[abc].id"],
)
def test_is_supported_json_path_rejects_unsupported_syntax(path: str) -> None:
    assert not is_supported_json_path(path)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "$",
            {
                "orders": [{"order_id": "ORD-123"}, {"order_id": "ORD-456"}],
                "customer": {"profile": {"id": "CUS-1"}},
                "line-items": [{"sku": "SKU-1"}],
            },
        ),
        ("$.orders[0].order_id", "ORD-123"),
        ("$.orders[1].order_id", "ORD-456"),
        ("$.customer.profile.id", "CUS-1"),
        ("$.line-items[0].sku", "SKU-1"),
    ],
)
def test_json_path_get_resolves_supported_paths(path: str, expected: object) -> None:
    payload = {
        "orders": [{"order_id": "ORD-123"}, {"order_id": "ORD-456"}],
        "customer": {"profile": {"id": "CUS-1"}},
        "line-items": [{"sku": "SKU-1"}],
    }

    assert json_path_get(payload, path) == expected


@pytest.mark.parametrize("path", ["$.orders[9].order_id", "$.orders[*].id", "$..order_id"])
def test_json_path_get_returns_none_for_missing_or_unsupported_paths(path: str) -> None:
    payload = {"orders": [{"order_id": "ORD-123"}]}

    assert json_path_get(payload, path) is None
