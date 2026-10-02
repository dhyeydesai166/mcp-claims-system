from datetime import date
import json
from pathlib import Path


def _load_json(filename: str) -> dict:
    path = Path(__file__).with_name(filename)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_employee_info(employee_id: str) -> dict:
    """Return role, tenure, and equipment for one employee id."""
    employees = _load_json("employees.json")
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
    policies = _load_json("policies.json")
    if role not in policies:
        raise KeyError(f"Unknown role: {role}")
    return {
        "role": role,
        "limits": policies[role],
    }


def check_request_eligibility(
    employee_id: str,
    item: str,
    today: date | None = None,
) -> dict:
    """Decide approve, deny, or escalate for one employee and one item."""
    if today is None:
        today = date.today()
    info = get_employee_info(employee_id)
    limits = get_policy_limits(str(info["role"]))["limits"]
    rule = next(
        (limit for limit in limits if limit["item"] == item),
        None,
    )
    if rule is None:
        return {
            "employee_id": employee_id,
            "item": item,
            "decision": "escalate",
            "reason": f"{item} is not covered for role {info['role']}",
        }
    owned = [
        piece for piece in info["equipment"] if piece["item"] == item
    ]
    if not owned:
        return {
            "employee_id": employee_id,
            "item": item,
            "decision": "approve",
            "reason": f"No {item} on file",
        }
    newest = max(owned, key=lambda piece: piece["issued_on"])
    issued_on = date.fromisoformat(newest["issued_on"])
    next_eligible = issued_on.replace(
        year=issued_on.year + int(rule["refresh_years"])
    )
    if today < next_eligible:
        return {
            "employee_id": employee_id,
            "item": item,
            "decision": "deny",
            "reason": (
                f"Newest {item} was issued {newest['issued_on']}. "
                f"Next eligible date is {next_eligible.isoformat()}"
            ),
        }
    return {
        "employee_id": employee_id,
        "item": item,
        "decision": "approve",
        "reason": (
            f"Newest {item} is due on {next_eligible.isoformat()}"
        ),
    }


def flag_for_human_review(
    employee_id: str,
    request: str,
    reason: str,
    queue_path: Path | None = None,
) -> dict:
    """Append one escalation record. Reject an empty field or unknown id."""
    if not employee_id.strip() or not request.strip() or not reason.strip():
        raise ValueError("employee_id, request, and reason are required")
    get_employee_info(employee_id)
    path = queue_path or Path(__file__).with_name("review_queue.json")
    if path.exists():
        queue = json.loads(path.read_text(encoding="utf-8"))
    else:
        queue = []
    record = {
        "employee_id": employee_id,
        "request": request,
        "reason": reason,
    }
    queue.append(record)
    path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    return record
