import json

import claims.tools as claims
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("equipment-requests")


@mcp.tool(structured_output=False)
def get_employee_info(employee_id: str) -> str:
    """Return role, tenure, and equipment for one existing employee id.

    Use this when you have an employee id. Do not use it to read policy rules.
    """
    return json.dumps(claims.get_employee_info(employee_id))


@mcp.tool(structured_output=False)
def get_policy_limits(role: str) -> str:
    """Return the item limits for one role, such as standard or manager.

    Use this after the employee's role is known. Do not use it to look up a person.
    """
    return json.dumps(claims.get_policy_limits(role))


@mcp.tool(structured_output=False)
def check_request_eligibility(employee_id: str, item: str) -> str:
    """Decide approve, deny, or escalate for one employee and one catalog item.

    The check uses today's date. Do not pass a date. Do not use this when the
    request does not name one item.
    """
    return json.dumps(claims.check_request_eligibility(employee_id, item))


@mcp.tool(structured_output=False)
def flag_for_human_review(employee_id: str, request: str, reason: str) -> str:
    """Append one escalation record for an existing employee.

    Use this only when the case is ambiguous. Do not use it to approve or deny.
    """
    return json.dumps(claims.flag_for_human_review(employee_id, request, reason))


if __name__ == "__main__":
    mcp.run(transport="stdio")
