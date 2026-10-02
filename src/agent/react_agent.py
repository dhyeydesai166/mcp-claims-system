import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA_URL = "http://host.docker.internal:11434/api/chat"
REACT_MODEL = "qwen3:8b"
REFLECT_MODEL = "gemma3:12b"
MAX_STEPS = 6
NEEDS_EMPLOYEE_ID = {
    "get_employee_info",
    "check_request_eligibility",
    "flag_for_human_review",
}


def server_parameters() -> StdioServerParameters:
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(root / "src")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "claims.server"],
        env=env,
    )


def ask_model(
    messages: list[dict[str, str]],
    model: str,
    think: bool,
    temperature: float,
) -> tuple[str, str]:
    body = {
        "model": model,
        "think": think,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": messages,
    }
    encoded = json.dumps(body).encode("utf-8")
    http_request = urllib.request.Request(
        OLLAMA_URL,
        data=encoded,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(http_request, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    message = payload["message"]
    content = message.get("content", "")
    thinking = message.get("thinking", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{model} returned no text")
    if not isinstance(thinking, str):
        thinking = ""
    return content, thinking


def parse_action(content: str) -> tuple[str, str, dict[str, Any]]:
    thought = ""
    action = ""
    raw_input = "{}"
    for line in content.splitlines():
        if line.startswith("Thought:"):
            thought = line.split(":", 1)[1].strip()
        elif line.startswith("Action:"):
            action = line.split(":", 1)[1].strip()
        elif line.startswith("Input:"):
            raw_input = line.split(":", 1)[1].strip()
    try:
        arguments = json.loads(raw_input) if raw_input else {}
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return thought, action, arguments


def tool_text(result: Any) -> str:
    texts = []
    for block in result.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(texts) if texts else str(result)


def tool_decision(observations: list[str]) -> str:
    for observation in reversed(observations):
        if '"decision": "approve"' in observation:
            return "approve"
        if '"decision": "deny"' in observation:
            return "deny"
        if '"decision": "escalate"' in observation:
            return "escalate"
    return ""


def reflect(draft: str, observations: list[str]) -> None:
    observed = tool_decision(observations)
    messages = [
        {
            "role": "system",
            "content": (
                "You check one draft against tool observations. "
                "Reply with exactly three lines:\n"
                "Verdict: confirm or conflict\n"
                "Decision: approve or deny or escalate\n"
                "Reply: one sentence that copies the tool decision\n"
                "confirm only when the draft decision matches the "
                "observations. Do not invent a date or an item."
            ),
        },
        {
            "role": "user",
            "content": (
                "Observations:\n"
                + "\n".join(observations)
                + f"\n\nDraft:\n{draft}"
            ),
        },
    ]
    content, thinking = ask_model(messages, REFLECT_MODEL, False, 0.2)
    if thinking:
        print("Thinking:", thinking)
    print("Reflection:", content)
    verdict = "conflict"
    for line in content.splitlines():
        if line.startswith("Verdict:"):
            verdict = line.split(":", 1)[1].strip().lower()
    reflected = ""
    for line in content.splitlines():
        if line.startswith("Decision:"):
            reflected = line.split(":", 1)[1].strip().lower()
    agrees = verdict == "confirm" and (
        not observed or reflected == observed
    )
    if agrees:
        print("Reflection confirmed the draft")
        print("Final:", draft)
        return
    print("Reflection caught the draft")
    if observed:
        print("Final:", f"The request is a {observed} based on the tools.")
        return
    print("Final:", draft)


async def main() -> None:
    employee_id = "E101"
    request = "I need a monitor."
    print("employee_id:", employee_id)
    print("request:", request)
    async with stdio_client(server_parameters()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [tool.name for tool in listed.tools]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You handle one equipment request. "
                        f"The employee id is {employee_id}. "
                        "Copy that id exactly. Do not invent another one. "
                        f"Tools: {', '.join(names)}. "
                        "Every reply is exactly three lines. "
                        "The Action line is never blank.\n"
                        "Example tool call:\n"
                        "Thought: the role is still unknown\n"
                        "Action: get_employee_info\n"
                        f"Input: {{\"employee_id\": \"{employee_id}\"}}\n"
                        "check_request_eligibility takes employee_id and item. "
                        "The key is item, not request.\n"
                        "Example eligibility call:\n"
                        "Thought: the item is a monitor\n"
                        "Action: check_request_eligibility\n"
                        f"Input: {{\"employee_id\": \"{employee_id}\", "
                        "\"item\": \"monitor\"}}\n"
                        "If a tool rejects an argument, call that same tool "
                        "again with the correct key. Do not flag that mistake.\n"
                        "When an observation contains a decision, "
                        "copy that decision and stop. Do not call another tool.\n"
                        "Example finish after an approve observation:\n"
                        "Thought: eligibility returned approve\n"
                        "Action: finish\n"
                        "Input: {\"decision\": \"approve\", "
                        "\"reply\": \"Your request is approved.\"}"
                    ),
                },
                {"role": "user", "content": request},
            ]
            observations: list[str] = []
            draft = ""
            for _ in range(MAX_STEPS):
                content, thinking = ask_model(
                    messages, REACT_MODEL, True, 0.6
                )
                if thinking:
                    print("Thinking:", thinking)
                thought, action, arguments = parse_action(content)
                if action in NEEDS_EMPLOYEE_ID:
                    arguments["employee_id"] = employee_id
                print("Thought:", thought)
                print("Action:", action)
                print("Input:", json.dumps(arguments))
                if action == "finish":
                    draft = str(arguments.get("reply", ""))
                    print("Draft:", draft)
                    break
                if action not in names:
                    observation = f"Unknown tool: {action}"
                elif action == "flag_for_human_review":
                    request_text = str(arguments.get("request", "")).strip()
                    reason = str(arguments.get("reason", "")).strip()
                    if not request_text or not reason:
                        observation = "flag needs a request and a reason"
                    else:
                        arguments["request"] = request_text
                        arguments["reason"] = reason
                        result = await session.call_tool(action, arguments)
                        observation = tool_text(result)
                else:
                    result = await session.call_tool(action, arguments)
                    observation = tool_text(result)
                print("Observation:", observation)
                observations.append(observation)
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {"role": "user", "content": f"Observation: {observation}"}
                )
            else:
                draft = "stopped after the step limit"
                print("Draft:", draft)
            reflect(draft, observations)


if __name__ == "__main__":
    asyncio.run(main())
