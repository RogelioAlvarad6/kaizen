"""Chat assistant: talks to you, uses wiki/habit tools, and can run your workflows."""
from __future__ import annotations

import json

from . import db, engine, habits, llm, tools
from .config import DEFAULT_MODEL

SYSTEM = """You are the user's personal assistant inside "SIMS AI Office", a local app on their Windows PC.
Their long-term memory is an Obsidian wiki (the AI-Wiki folder of their vault) that you can read and write.

Their goals: take the gym seriously, read every day, earn cybersecurity certifications (currently {cert}),
grow their financial literacy (education only - never give personalized investment advice), and grow as a developer.

How to help:
- Questions about things they've learned: search/read the wiki first and cite pages as [[wikilinks]].
- Habit check-ins ("did 30 min reading, push day at the gym"): log each item with habit_log, then reply with
  progress vs goals and a short encouraging note. Ask a follow-up if an amount is ambiguous.
- If a saved workflow fits the request (e.g. ingest new sources, weekly report), call run_workflow.
- Use web search for current information when needed.
Be concise and practical. Today is {today}.

Saved workflows you can run:
{workflows}"""


def _workflow_tools() -> list[tools.Tool]:
    def list_workflows() -> str:
        return json.dumps([{"id": w["id"], "name": w["name"], "description": w["description"]} for w in db.list_workflows() if w["enabled"]])

    def run_workflow(workflow_id: str, input: str = "") -> str:
        run_id = engine.start_run(workflow_id, "chat", input, {})
        r = engine.wait_for(run_id, timeout=600)
        if not r or r["status"] == "running":
            return f"Workflow still running (run {run_id}); check the Runs page."
        if r["status"] == "error":
            return f"Workflow failed: {r['error']}"
        return r["output"] or "(workflow finished with no output)"

    return [
        tools.Tool("list_workflows", "List the user's saved workflows.", {"type": "object", "properties": {}, "additionalProperties": False}, list_workflows),
        tools.Tool("run_workflow", "Run a saved workflow by id and wait for its output. 'input' becomes the workflow's {{input}}.",
                   {"type": "object", "properties": {"workflow_id": {"type": "string"}, "input": {"type": "string"}},
                    "required": ["workflow_id"], "additionalProperties": False}, run_workflow),
    ]


def get(chat_id: str) -> dict | None:
    row = db.one("SELECT * FROM chats WHERE id = ?", (chat_id,))
    if row:
        row["display"] = json.loads(row["display"] or "[]")
        row.pop("messages", None)
    return row


def list_chats() -> list[dict]:
    return db.query("SELECT id, title, updated_at, cost_usd FROM chats ORDER BY updated_at DESC LIMIT 50")


def delete(chat_id: str) -> None:
    db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def send(chat_id: str | None, message: str, model: str | None = None, effort: str | None = None) -> dict:
    row = db.one("SELECT * FROM chats WHERE id = ?", (chat_id,)) if chat_id else None
    if row:
        messages, display, cost = json.loads(row["messages"]), json.loads(row["display"]), row["cost_usd"] or 0
    else:
        chat_id, messages, display, cost = db.new_id(), [], [], 0.0
        db.execute("INSERT INTO chats(id, title, messages, display, cost_usd, updated_at) VALUES (?,?,?,?,?,?)",
                   (chat_id, message[:60], "[]", "[]", 0, db.now()))

    wfs = "\n".join(f"- {w['id']}: {w['name']} - {w['description']}" for w in db.list_workflows() if w["enabled"]) or "(none)"
    system = SYSTEM.format(cert=habits.goals()["current_cert"], today=db.now()[:10], workflows=wfs)
    defs, handler = tools.build(["wiki_read", "wiki_write", "habits", "web"], extra=_workflow_tools())

    start = len(messages)
    messages.append({"role": "user", "content": message})
    display.append({"role": "user", "text": message})
    try:
        res = llm.run_agent(system=system, messages=messages, tool_defs=defs, tool_handler=handler,
                            model=model or DEFAULT_MODEL, effort=effort or "medium", max_turns=20, source="chat")
        display.append({"role": "assistant", "text": res.text, "tools": [t["name"] for t in res.tool_calls], "cost": res.cost})
        cost += res.cost
    except llm.AgentError as e:
        # Drop this failed turn so the stored conversation stays a valid, append-only history.
        del messages[start:]
        display.append({"role": "error", "text": str(e)})

    db.execute("UPDATE chats SET messages=?, display=?, cost_usd=?, updated_at=? WHERE id=?",
               (json.dumps(messages, ensure_ascii=False), json.dumps(display, ensure_ascii=False), cost, db.now(), chat_id))
    return {"id": chat_id, "display": display, "cost_usd": cost}
