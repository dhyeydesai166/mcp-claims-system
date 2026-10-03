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
REACT_MODEL = "gemma3:4b"
REFLECT_MODEL = "gemma3:12b"
MAX_STEPS = 6
MAX_REFLECTION = 2
NEEDS_EMPLOYEE_ID = {
    "get_employee_info",
    "check_request_eligibility",
    "flag_for_human_review",
}


def load_demos() -> list[dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "claims" / "demos.json"
    with path.open(encoding="utf-8") as handle:
        demos = json.load(handle)
    return demos


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


def draft_matches(draft: str, observed: str) -> bool:
    if not observed:
        return True
    return observed in draft.lower()


def _reflection_prompt(
    request_text: str,
    decision: str,
    draft: str,
    trace: str,
) -> str:
    return (
        "You are reviewing a drafted reply and a proposed decision "
        "before either is final. "
        "Reply with exactly three lines:\n"
        "Verdict: pass or rewrite or missing_facts or escalate\n"
        "Reply: one sentence\n"
        "Reason: one short clause\n"
        "Ask two questions. pass only when both answers are yes.\n"
        "Does this satisfy the request?\n"
        "Does the tool trace support the draft and the proposed "
        "decision?\n"
        "The proposed decision came from the tools. "
        "It may be approve, deny, or escalate. "
        "That word is evidence, not your verdict.\n"
        "pass when both questions are yes, including when "
        "Decision is escalate and the draft sends the case "
        "to a human. Do not write Verdict escalate in that case.\n"
        "rewrite when the decision is right but the wording is wrong. "
        "Put the revised sentence on the Reply line.\n"
        "missing_facts when the trace does not support a fact "
        "in the draft, or a tool result is absent.\n"
        "Verdict escalate means only that you cannot answer "
        "the two questions. Never copy the Decision word.\n"
        "Print only the three lines. Do not repeat the questions.\n"
        "Do not invent a date or an item.\n"
        "Example when Decision is escalate and the draft agrees:\n"
        "Verdict: pass\n"
        "Reply: Your request needs a human review.\n"
        "Reason: the trace supports escalate\n\n"
        "Request:\n"
        + request_text
        + "\n\nDecision:\n"
        + decision
        + "\n\nDraft:\n"
        + draft
        + "\n\nTool trace:\n"
        + trace
        + "\n"
    )


def reflect(
    request_text: str,
    decision: str,
    draft: str,
    observations: list[str],
) -> dict[str, str]:
    messages = [
        {
            "role": "user",
            "content": _reflection_prompt(
                request_text,
                decision,
                draft,
                "\n".join(observations),
            ),
        },
    ]
    content, thinking = ask_model(messages, REFLECT_MODEL, False, 0.2)
    if thinking:
        print("Thinking:", thinking)
    print("Reflection:", content)
    verdict = "escalate"
    reply = ""
    reason = ""
    for line in content.splitlines():
        if line.startswith("Verdict:"):
            verdict = line.split(":", 1)[1].strip().lower()
        elif line.startswith("Reply:"):
            reply = line.split(":", 1)[1].strip()
        elif line.startswith("Reason:"):
            reason = line.split(":", 1)[1].strip()
    allowed = {"pass", "rewrite", "missing_facts", "escalate"}
    if verdict not in allowed:
        verdict = "escalate"
    if (
        verdict == "escalate"
        and decision == "escalate"
        and draft_matches(draft, decision)
    ):
        verdict = "pass"
    if not reason:
        reason = "reflection could not confirm the draft"
    return {"verdict": verdict, "reply": reply, "reason": reason}


async def main() -> None:
    async with stdio_client(server_parameters()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [tool.name for tool in listed.tools]
            for demo in load_demos():
                employee_id = demo["employee_id"]
                request = demo["request"]
                print("=" * 40)
                print("employee_id:", employee_id)
                print("request:", request)
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
                            "The only catalog items are monitor and laptop. "
                            "Use an item only if the employee's sentence names it. "
                            "Do not choose an item from equipment already on file. "
                            "If the sentence names an item, even one not in "
                            "the catalog, call check_request_eligibility "
                            "with that item.\n"
                            "Example when the sentence names an item "
                            "that is not in the catalog:\n"
                            "Thought: the sentence names a phone\n"
                            "Action: check_request_eligibility\n"
                            f"Input: {{\"employee_id\": \"{employee_id}\", "
                            "\"item\": \"phone\"}}\n"
                            "If the sentence names no item, "
                            "call flag_for_human_review once. "
                            "That tool needs employee_id, request, and reason. "
                            "request is the employee's sentence. "
                            "reason is that the sentence names no item.\n"
                            "Example when no item is named:\n"
                            "Thought: the sentence names no item\n"
                            "Action: flag_for_human_review\n"
                            f"Input: {{\"employee_id\": \"{employee_id}\", "
                            "\"request\": \"My setup is terrible\", "
                            "\"reason\": \"the sentence names no item\"}}\n"
                            "If a tool rejects an argument, call that same tool "
                            "again with the correct key. Do not flag that mistake.\n"
                            "When an observation contains decision approve "
                            "or deny, copy that decision and stop. "
                            "Do not call another tool. Do not flag it.\n"
                            "Example finish after an approve observation:\n"
                            "Thought: eligibility returned approve\n"
                            "Action: finish\n"
                            "Input: {\"decision\": \"approve\", "
                            "\"reply\": \"Your request is approved.\"}\n"
                            "Example finish after a deny observation:\n"
                            "Thought: eligibility returned deny\n"
                            "Action: finish\n"
                            "Input: {\"decision\": \"deny\", "
                            "\"reply\": \"Your request is denied.\"}\n"
                            "Only decision escalate uses flag_for_human_review "
                            "after eligibility. Do not finish on escalate. "
                            "The next action is flag_for_human_review. "
                            "request is the employee's sentence. "
                            "reason is that the item is not covered.\n"
                            "Example after an escalate observation:\n"
                            "Thought: eligibility returned escalate\n"
                            "Action: flag_for_human_review\n"
                            f"Input: {{\"employee_id\": \"{employee_id}\", "
                            "\"request\": \"I need a new iPhone\", "
                            "\"reason\": \"phone is not covered\"}}\n"
                            "When an observation is from flag_for_human_review, "
                            "stop. Do not call that tool again."
                        ),
                    },
                    {"role": "user", "content": request},
                ]
                observations: list[str] = []
                draft = ""
                reflection_tries = 0
                finished = False
                for _ in range(MAX_STEPS):
                    content, thinking = ask_model(
                        messages, REACT_MODEL, False, 0.6
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
                        while True:
                            grade = reflect(
                                request,
                                tool_decision(observations),
                                draft,
                                observations,
                            )
                            if grade["verdict"] == "pass":
                                print("Reflection confirmed the draft")
                                print("Final:", draft)
                                finished = True
                                break
                            if (
                                grade["verdict"] == "escalate"
                                or reflection_tries >= MAX_REFLECTION
                            ):
                                reason = grade["reason"]
                                result = await session.call_tool(
                                    "flag_for_human_review",
                                    {
                                        "employee_id": employee_id,
                                        "request": request,
                                        "reason": reason,
                                    },
                                )
                                print("Observation:", tool_text(result))
                                print("Final: Your request needs a human review.")
                                finished = True
                                break
                            if grade["verdict"] == "rewrite":
                                revised = grade["reply"]
                                observed = tool_decision(observations)
                                if revised and draft_matches(revised, observed):
                                    draft = revised
                                    print("Revised draft:", draft)
                                else:
                                    print("Rewrite ignored; draft decision unchanged")
                                print("Reflection confirmed the draft")
                                print("Final:", draft)
                                finished = True
                                break
                            note = grade["reason"]
                            print("Reflection sent the case back to ReAct")
                            messages.append({"role": "assistant", "content": content})
                            messages.append(
                                {
                                    "role": "user",
                                    "content": f"Reflection: {note}",
                                }
                            )
                            break
                        if finished:
                            break
                        continue
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
                    if (
                        action == "flag_for_human_review"
                        and not observation.startswith("flag needs")
                    ):
                        print("Final: Your request needs a human review.")
                        finished = True
                        break
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {"role": "user", "content": f"Observation: {observation}"}
                    )
                if not finished:
                    result = await session.call_tool(
                        "flag_for_human_review",
                        {
                            "employee_id": employee_id,
                            "request": request,
                            "reason": "stopped after the step limit",
                        },
                    )
                    print("Observation:", tool_text(result))
                    print("Draft: stopped after the step limit")
                    print("Final: Your request needs a human review.")


if __name__ == "__main__":
    asyncio.run(main())
