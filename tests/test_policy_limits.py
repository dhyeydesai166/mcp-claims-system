import pytest

from claims.tools import get_policy_limits


def test_get_policy_limits_returns_standard_rules() -> None:
    limits = get_policy_limits("standard")
    assert limits["role"] == "standard"
    assert limits["limits"] == [
        {"item": "monitor", "max_count": 1, "refresh_years": 3},
        {"item": "laptop", "max_count": 1, "refresh_years": 4},
    ]


def test_get_policy_limits_unknown_role_raises() -> None:
    with pytest.raises(KeyError):
        get_policy_limits("intern")
