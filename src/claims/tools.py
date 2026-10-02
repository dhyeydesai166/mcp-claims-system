import json
from pathlib import Path


def load_data() -> dict:
    path = Path(__file__).with_name("data.json")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_employee_info(employee_id: str) -> dict:
    """Return role, tenure, and equipment for one employee id."""
    data = load_data()
    employees = data["employees"]
    if employee_id not in employees:
        raise KeyError(f"Unknown employee id: {employee_id}")
    employee = employees[employee_id]
    return {
        "employee_id": employee_id,
        "name": employee["name"],
        "role": employee["role"],
        "tenure_years": employee["tenure_years"],
        "equipment": employee["equipment"],
    }


def get_policy_limits(role: str) -> dict:
    """Return the item limits for one role."""
    data = load_data()
    policies = data["policies"]
    if role not in policies:
        raise KeyError(f"Unknown role: {role}")
    return {
        "role": role,
        "limits": policies[role],
    }
