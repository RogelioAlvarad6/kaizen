"""FastAPI server: REST API for the canvas UI + background triggers.

Run (from backend/):  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import blocks, chat, db, engine, habits, nudges, seed, tools, tracker, triggers, wiki, xp
from .config import DEFAULT_MODEL, FRONTEND_DIST, MODELS, MONTHLY_BUDGET_USD, VAULT_PATH, WIKI_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


# The AI side (chat, Obsidian wiki, scheduled workflows) is parked for now: the app is a goal tracker.
# Set ENABLE_AI_AUTOMATIONS=true in backend/.env to turn schedules + the raw/ folder watcher back on.
AI_AUTOMATIONS = os.getenv("ENABLE_AI_AUTOMATIONS", "false").lower() == "true"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.conn()
    tracker.init()
    seed.seed()
    nudges.start()
    if AI_AUTOMATIONS:
        if VAULT_PATH.exists():
            wiki.ensure_structure()
        triggers.start()
    yield
    nudges.stop()
    if AI_AUTOMATIONS:
        triggers.stop()


app = FastAPI(title="SIMS AI Office", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# ---- models ------------------------------------------------------------------
class WorkflowIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    enabled: bool = True
    graph: dict


class RunIn(BaseModel):
    input: str = ""


class ChatIn(BaseModel):
    chat_id: str | None = None
    message: str
    model: str | None = None
    effort: str | None = None


class HabitIn(BaseModel):
    kind: str
    value: float = 1
    unit: str = ""
    note: str = ""
    day: str | None = None


class GoalIn(BaseModel):
    id: int | None = None
    name: str
    category: str = "personal"
    kind: str = "number"
    unit: str = "min"
    target: float = 1
    period: str = "daily"
    step: float = 15
    sort: int | None = None
    deadline: str | None = None      # YYYY-MM-DD, or "" to clear
    total_target: float | None = None
    start_date: str | None = None
    completed_at: str | None = None


class LogIn(BaseModel):
    goal_id: int
    day: str
    value: float
    note: str | None = None


# ---- goal tracker --------------------------------------------------------------
@app.get("/api/goals")
def goals(include_archived: bool = False):
    return tracker.list_goals(include_archived)


@app.post("/api/goals")
def save_goal(body: GoalIn):
    if body.category not in ("personal", "professional") or body.period not in ("daily", "weekly") or body.kind not in ("number", "check"):
        raise HTTPException(400, "invalid category, period or kind")
    if not body.name.strip() or body.target <= 0:
        raise HTTPException(400, "goal needs a name and a target above 0")
    return tracker.save_goal(body.model_dump(exclude_none=True))


@app.post("/api/goals/{gid}/archive")
def archive_goal(gid: int, archived: bool = True):
    tracker.archive_goal(gid, archived)
    return {"ok": True}


@app.get("/api/day/{day}")
def day_view(day: str):
    return tracker.day_view(day)


@app.post("/api/log")
def set_log(body: LogIn):
    return tracker.set_log(body.goal_id, body.day, body.value, body.note)


@app.get("/api/stats")
def stats(days: int = 84):
    return tracker.stats(max(28, min(days, 365)))


@app.get("/api/xp")
def xp_summary():
    return xp.compute()


@app.get("/api/notify")
def notify_status():
    return {"configured": nudges.configured(), "mention": bool(os.getenv("DISCORD_USER_ID", "").strip()),
            "settings": nudges.settings(), "next_runs": nudges.next_runs()}


@app.put("/api/notify")
def notify_update(body: dict):
    for k, v in body.items():
        if k in nudges.SETTINGS:
            db.set_setting(k, str(v))
    nudges.reload()
    return notify_status()


@app.post("/api/notify/send/{kind}")
def notify_send(kind: str):
    """Test buttons: 'test' sends a hello; behind/streak/weekly send that message now, even if all is on track."""
    if kind not in ("test", "behind", "streak", "weekly"):
        raise HTTPException(404, "unknown message kind")
    try:
        if kind == "test":
            nudges.send("Kaizen is connected ✓", ["Nudges will land in this channel.", f"Open Kaizen: `{nudges.APP_URL}`"], nudges.GREEN)
            return {"result": "sent"}
        return {"result": nudges.run(kind, force=True)}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/goals/{gid}/complete")
def complete_goal(gid: int, done: bool = True):
    """Mark a deadline goal (e.g. a certification) as completed - or undo it."""
    db.execute("UPDATE goals SET completed_at = ? WHERE id = ?", (db.now()[:10] if done else None, gid))
    return {"ok": True}


# ---- meta --------------------------------------------------------------------
@app.get("/api/status")
def status():
    return {
        "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "vault_path": str(VAULT_PATH), "vault_exists": VAULT_PATH.exists(),
        "wiki_root": str(WIKI_ROOT), "wiki_exists": WIKI_ROOT.exists(),
        "default_model": DEFAULT_MODEL,
        "month_spend_usd": round(db.month_spend(), 4), "monthly_budget_usd": MONTHLY_BUDGET_USD,
        "scheduled": triggers.scheduled_jobs(),
        "pending_raw": wiki.pending_raw() if WIKI_ROOT.exists() else [],
        "wiki_pages": len(wiki.list_files("wiki")) if WIKI_ROOT.exists() else 0,
    }


@app.get("/api/blocks")
def list_blocks():
    return {"blocks": blocks.catalog(), "models": MODELS, "tool_groups": {k: v["label"] for k, v in tools.GROUPS.items()}}


# ---- workflows ---------------------------------------------------------------
@app.get("/api/workflows")
def list_workflows():
    return db.list_workflows()


@app.get("/api/workflows/{wf_id}")
def get_workflow(wf_id: str):
    wf = db.get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    return wf


@app.post("/api/workflows")
def save_workflow(body: WorkflowIn):
    wf = db.save_workflow(body.model_dump())
    triggers.reload_schedules()
    return wf


@app.delete("/api/workflows/{wf_id}")
def delete_workflow(wf_id: str):
    db.delete_workflow(wf_id)
    triggers.reload_schedules()
    return {"ok": True}


@app.post("/api/workflows/{wf_id}/run")
def run_workflow(wf_id: str, body: RunIn):
    try:
        return {"run_id": engine.start_run(wf_id, "manual", body.input)}
    except KeyError as e:
        raise HTTPException(404, str(e))


# ---- runs --------------------------------------------------------------------
@app.get("/api/runs")
def list_runs(workflow_id: str | None = None, limit: int = 50):
    sql = "SELECT id, workflow_id, workflow_name, trigger, status, error, cost_usd, started_at, finished_at FROM runs"
    params: list = []
    if workflow_id:
        sql += " WHERE workflow_id = ?"
        params.append(workflow_id)
    return db.query(sql + " ORDER BY started_at DESC LIMIT ?", [*params, limit])


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    r = engine.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


# ---- chat --------------------------------------------------------------------
@app.get("/api/chats")
def chats():
    return chat.list_chats()


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str):
    c = chat.get(chat_id)
    if not c:
        raise HTTPException(404, "chat not found")
    return c


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    chat.delete(chat_id)
    return {"ok": True}


@app.post("/api/chat")
def send_chat(body: ChatIn):
    return chat.send(body.chat_id, body.message, body.model, body.effort)


# ---- habits & goals ----------------------------------------------------------
@app.get("/api/habits")
def get_habits(days: int = 14):
    g = habits.goals()
    return {"entries": habits.entries(days), "daily": habits.daily_totals(days), "goals": g,
            "streaks": {"reading": habits.streak("reading", g["reading_goal_minutes"]), "study": habits.streak("study", 1)},
            "kinds": habits.KINDS}


@app.get("/api/progress")
def get_progress(days: int = 84):
    return habits.progress(max(7, min(days, 365)))


@app.post("/api/habits")
def add_habit(body: HabitIn):
    return habits.log(body.kind, body.value, body.unit, body.note, body.day)


@app.delete("/api/habits/{hid}")
def delete_habit(hid: int):
    habits.delete(hid)
    return {"ok": True}


@app.put("/api/settings")
def update_settings(body: dict):
    for k, v in body.items():
        if k in db.DEFAULT_SETTINGS:
            db.set_setting(k, str(v))
    return db.get_settings()


@app.get("/api/settings")
def get_settings():
    return db.get_settings()


# ---- serve the built frontend (npm run build) ---------------------------------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else FRONTEND_DIST / "index.html")
