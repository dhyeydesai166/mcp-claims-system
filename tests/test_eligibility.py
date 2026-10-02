from datetime import date

import pytest

from claims.tools import check_request_eligibility


def test_monitor_with_none_on_file_is_approved() -> None:
    result = check_request_eligibility(
        "E101", "monitor", today=date(2026, 10, 2)
    )
    assert result["decision"] == "approve"


def test_recent_monitor_is_denied() -> None:
    result = check_request_eligibility(
        "E102", "monitor", today=date(2026, 10, 2)
    )
    assert result["decision"] == "deny"


def test_same_monitor_is_approved_on_the_eligible_date() -> None:
    result = check_request_eligibility(
        "E102", "monitor", today=date(2028, 11, 1)
    )
    assert result["decision"] == "approve"


def test_item_not_in_the_catalog_is_escalated() -> None:
    result = check_request_eligibility(
        "E103", "phone", today=date(2026, 10, 2)
    )
    assert result["decision"] == "escalate"


def test_unknown_employee_raises() -> None:
    with pytest.raises(KeyError):
        check_request_eligibility(
            "E999", "monitor", today=date(2026, 10, 2)
        )
