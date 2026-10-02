import pytest

from claims.tools import get_employee_info


def test_get_employee_info_returns_role_tenure_and_equipment() -> None:
    info = get_employee_info("E101")
    assert info["role"] == "standard"
    assert info["tenure_years"] == 2
    assert info["equipment"] == [
        {"item": "laptop", "issued_on": "2024-06-01"}
    ]


def test_get_employee_info_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        get_employee_info("E999")
