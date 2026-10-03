# What we built

This project handles one IT equipment ask at a time.

The employee gives an id (like E101) and one sentence (like "I need a monitor.").
The system looks up that person and the role rules, then says yes, no, or send it to a human.

There are two programs:

- **Server** (`src/claims/server.py`): four tools. It reads JSON files and writes the review queue.
- **Agent** (`src/agent/react_agent.py`): starts the server, talks to it over stdin/stdout, and asks a model what to do next.

The four tools:

1. `get_employee_info` : role, tenure, equipment on file
2. `get_policy_limits` : what that role can have and how often
3. `check_request_eligibility` : approve, deny, or escalate for one item
4. `flag_for_human_review` : write one row to the review queue

Rules (short):

- Catalog items are monitor and laptop.
- Approve if the item is allowed and they can have it now.
- Deny if the item is allowed but it is too soon (or they are at the max).
- Escalate if no item is named, or the item is not in the catalog (phone, desk).
- Unknown employee id is an error. We do not approve it.

Two models:

- **ReAct** (`gemma3:4b`): picks the next tool and writes a draft.
- **Reflection** (`gemma3:12b`): checks the draft against the tool results.

---

# How one request flows

```text
employee id + sentence
        |
        v
   start MCP server (stdio)
        |
        v
   list tools
        |
        v
   +------------------ ReAct loop (max 6 turns) ------------------+
   |                                                              |
   |   model writes: Thought / Action / Input                     |
   |                      |                                       |
   |          +-----------+-----------+                           |
   |          |           |           |                           |
   |       finish      a tool      unknown tool                   |
   |          |           |           |                           |
   |          |           v           v                           |
   |          |      run the tool   "Unknown tool: ..."           |
   |          |           |                                       |
   |          |           v                                       |
   |          |      print Observation                            |
   |          |           |                                       |
   |          |     was it a good flag? ---- yes ----> Final      |
   |          |           |                         (human review)|
   |          |          no                                       |
   |          |           |                                       |
   |          |     add Observation to chat                       |
   |          |           |                                       |
   |          |           +---- back to the model (next turn)     |
   |          |                                                   |
   |          v                                                   |
   |     print Draft                                              |
   |          |                                                   |
   |          v                                                   |
   |     Reflection (gemma3:12b)                                  |
   |          |                                                   |
   |     pass / rewrite  ------------------> print Final          |
   |     missing_facts  ---> note back to ReAct (next turn)       |
   |     escalate / out of tries ---> flag, then Final            |
   |                                 (human review)               |
   +--------------------------------------------------------------+
        |
        | if the loop ended with no finish and no flag
        v
   flag (reason: step limit)
        |
        v
   Final: Your request needs a human review.
```

---

# What happens inside the ReAct loop

Each turn is the same shape.

1. The ReAct model sees the sentence, the tool list, and every Observation so far.
2. It must reply with three lines:
   - `Thought:` what is still missing
   - `Action:` the tool name, or `finish`
   - `Input:` JSON for that tool
3. The script prints those three lines.
4. Then one of these happens.

## A. The action is a real tool

The agent calls the MCP server. The server runs the Python function and sends JSON back. That JSON is the **Observation**.

Then:

- If the tool was `flag_for_human_review` and it worked, we stop.
  Final is always: `Your request needs a human review.`
  Reflection does not run on this path. The queue already has the row.
- If the tool was anything else (or the flag was missing a field), we add the Observation to the chat and loop. The model takes another turn.

Typical tool paths:

| Sentence | First tool | Observation | Next step |
| --- | --- | --- | --- |
| I need a monitor (E101) | eligibility | decision approve | finish |
| I need a monitor (E102) | eligibility | decision deny | finish |
| I need a new iPhone (E103) | eligibility | decision escalate | **flag**, then stop |
| My setup is terrible (E104) | flag | queue row written | stop |

Approve and deny must **not** flag. Only escalate (or a sentence with no item) flags.

## B. The action is `finish`

This is how approve and deny leave the loop.

1. We take the `reply` from Input. That is the **Draft**.
2. We do **not** call another tool yet.
3. We go to **Reflection**.

## C. The action is not a tool name

We do not crash. Observation is `Unknown tool: ...`. That goes back to the model so it can try again.

## D. We run out of turns

If we never finished and never flagged, the code flags with reason `stopped after the step limit`. Same Final as other human cases.

---

# What happens after ReAct (Reflection)

Reflection only runs after `finish` (the approve / deny draft).

We send four things to `gemma3:12b`:

- the employee sentence
- the tool decision (approve, deny, or escalate)
- the draft
- the tool trace

The grader answers two questions: does the draft match the request, and do the tools support it?

It must reply with one of:

| Verdict | Meaning | What we do |
| --- | --- | --- |
| pass | both questions are yes | print Final = the draft |
| rewrite | decision is right, wording is weak | keep a rewrite only if it still has the same decision; then print Final |
| missing_facts | a tool fact is missing | send the note back into ReAct for one more tool turn, then grade again |
| escalate | the grader is unsure | call `flag_for_human_review`, then Final is human review |

`Verdict: escalate` is **not** the same as a tool `decision: escalate`.
The tool word is evidence. The verdict means "I cannot confirm this draft."

---

# What happens after escalate

Escalate can show up in two places. Both end the same way for the employee.

**1. The eligibility tool says escalate** (item not in the catalog)

- Observation has `"decision": "escalate"`.
- The model must **not** finish yet.
- Next Action is `flag_for_human_review` with the sentence and a reason like "iPhone is not covered".
- That write is the record for a human.
- We stop. Final: `Your request needs a human review.`

**2. The sentence names no item**

- We skip eligibility.
- We flag at once with reason "the sentence names no item".
- Same Final.

**3. Reflection cannot confirm a draft**

- We flag with the grader's reason.
- Same Final.

So: escalate always means "write the queue, then say it needs a human."
Approve and deny mean "write a draft, let reflection check it, then print that draft."

---

# How the three parts connect

```text
  Agent (react_agent.py)
       |  starts process, stdin / stdout
       v
  MCP server (server.py)
       |  calls
       v
  tools.py  -->  employees.json (read)
            -->  policies.json (read)
            -->  review_queue.json (write on flag only)

  Agent also calls Ollama on the host:
    gemma3:4b   = which tool / finish
    gemma3:12b  = grade the draft
```

Unit tests call `tools.py` directly. They never start Ollama.
CI runs pytest, flake8, and mypy. The live four-demo run is local only.
