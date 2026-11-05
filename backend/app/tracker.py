"""Daily goal tracker: user-defined personal & professional goals, one log value per goal per day."""
from __future__ import annotations

from datetime import date, timedelta

from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'personal',   -- personal | professional
    kind TEXT NOT NULL DEFAULT 'number',         -- number | check
    unit TEXT NOT NULL DEFAULT 'min',
    target REAL NOT NULL DEFAULT 1,
    period TEXT NOT NULL DEFAULT 'daily',        -- daily | weekly
    step REAL NOT NULL DEFAULT 15,               -- size of the quick "+" button
    sort INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS logs (
    goal_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    PRIMARY KEY (goal_id, day)
);
"""

STARTER_GOALS = [
    # name, category, kind, unit, target, period, step, legacy habit kind
    ("Reading", "personal", "number", "min", 30, "daily", 10, "reading"),
    ("Gym", "personal", "number", "sessions", 4, "weekly", 1, "gym"),
    ("Security+ study", "professional", "number", "min", 45, "daily", 15, "study"),
    ("Financial literacy", "professional", "number", "min", 60, "weekly", 15, "finance"),
]


# Deadline goals (e.g. a certification): a total amount to finish by a date, tracked as a pace.
DEADLINE_COLUMNS = {"deadline": "TEXT", "total_target": "REAL", "start_date": "TEXT", "completed_at": "TEXT"}


def init() -> None:
    db.conn().executescript(SCHEMA)
    have = {r["name"] for r in db.query("PRAGMA table_info(goals)")}
    for col, typ in DEADLINE_COLUMNS.items():
        if col not in have:
            db.execute(f"ALTER TABLE goals ADD COLUMN {col} {typ}")
    if not db.one("SELECT id FROM goals LIMIT 1"):
        for i, (name, cat, kind, unit, target, period, step, legacy) in enumerate(STARTER_GOALS):
            gid = db.execute(
                "INSERT INTO goals(name, category, kind, unit, target, period, step, sort, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (name, cat, kind, unit, target, period, step, i, db.now()),
            )
            # carry over anything already logged in the old habits table
            for r in db.query("SELECT day, SUM(value) AS v, GROUP_CONCAT(note, '; ') AS n FROM habits WHERE kind = ? GROUP BY day", (legacy,)):
                db.execute("INSERT OR REPLACE INTO logs(goal_id, day, value, note, updated_at) VALUES (?,?,?,?,?)",
                           (gid, r["day"], r["v"] or 0, (r["n"] or "").strip("; "), db.now()))


# ---- goals -------------------------------------------------------------------
GOAL_FIELDS = ("name", "category", "kind", "unit", "target", "period", "step", "sort",
               "deadline", "total_target", "start_date", "completed_at")


def pace(g: dict, today: date | None = None) -> dict | None:
    """Progress toward a deadline goal: how much is left and the daily pace needed vs. your recent average."""
    if not g.get("deadline") or not g.get("total_target"):
        return None
    today = today or date.today()
    deadline = date.fromisoformat(g["deadline"])
    start = date.fromisoformat(g.get("start_date") or (g.get("created_at") or today.isoformat())[:10])
    done = db.one("SELECT COALESCE(SUM(value), 0) AS v FROM logs WHERE goal_id = ? AND day >= ? AND day <= ?",
                  (g["id"], start.isoformat(), today.isoformat()))["v"]  # type: ignore[index]
    logged_today = db.one("SELECT COALESCE(SUM(value), 0) AS v FROM logs WHERE goal_id = ? AND day = ?",
                          (g["id"], today.isoformat()))["v"]  # type: ignore[index]
    total = float(g["total_target"])
    remaining = max(0.0, total - done)
    days_left = (deadline - today).days + 1  # including today
    # pace needed per day, counted from the start of today (so logging today doesn't move today's target)
    need_per_day = (remaining + logged_today) / days_left if days_left > 0 else remaining
    window_start = max(start, today - timedelta(days=13))
    window_days = (today - window_start).days + 1
    recent = db.one("SELECT COALESCE(SUM(value), 0) AS v FROM logs WHERE goal_id = ? AND day >= ? AND day <= ?",
                    (g["id"], window_start.isoformat(), today.isoformat()))["v"]  # type: ignore[index]
    avg = recent / window_days
    if g.get("completed_at"):
        status = "completed"
    elif remaining <= 0:
        status = "done"
    elif days_left <= 0:
        status = "overdue"
    else:
        status = "on_pace" if avg >= need_per_day else "behind"
    return {"deadline": deadline.isoformat(), "start_date": start.isoformat(), "days_left": days_left, "total": total,
            "done": round(done, 2), "remaining": round(remaining, 2), "need_per_day": round(need_per_day, 1),
            "avg_per_day": round(avg, 1), "gap_per_day": round(max(0.0, need_per_day - avg), 1), "status": status}


def list_goals(include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM goals" + ("" if include_archived else " WHERE archived = 0") + " ORDER BY category, sort, id"
    return db.query(sql)


def save_goal(g: dict) -> dict:
    vals = {k: g[k] for k in GOAL_FIELDS if k in g}
    for k in DEADLINE_COLUMNS:  # "" clears a deadline field
        if vals.get(k) in ("", 0):
            vals[k] = None
    if vals.get("deadline") and not vals.get("start_date") and not g.get("id"):
        vals["start_date"] = date.today().isoformat()
    if vals.get("kind") == "check":
        vals.update(unit="done", step=1, target=vals.get("target", 1) if vals.get("period") == "weekly" else 1)
    if g.get("id"):
        sets = ", ".join(f"{k} = ?" for k in vals)
        db.execute(f"UPDATE goals SET {sets} WHERE id = ?", [*vals.values(), g["id"]])
        gid = g["id"]
    else:
        if "sort" not in vals:
            row = db.one("SELECT COALESCE(MAX(sort), -1) + 1 AS s FROM goals")
            vals["sort"] = row["s"] if row else 0
        cols = ", ".join([*vals, "created_at"])
        gid = db.execute(f"INSERT INTO goals({cols}) VALUES ({', '.join('?' * (len(vals) + 1))})", [*vals.values(), db.now()])
    return db.one("SELECT * FROM goals WHERE id = ?", (gid,))  # type: ignore[return-value]


def archive_goal(gid: int, archived: bool = True) -> None:
    db.execute("UPDATE goals SET archived = ? WHERE id = ?", (int(archived), gid))


# ---- logging -----------------------------------------------------------------
def set_log(goal_id: int, day: str, value: float, note: str | None = None) -> dict:
    value = max(0.0, float(value))
    existing = db.one("SELECT note FROM logs WHERE goal_id = ? AND day = ?", (goal_id, day))
    note = existing["note"] if note is None and existing else (note or "")
    db.execute(
        "INSERT INTO logs(goal_id, day, value, note, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(goal_id, day) DO UPDATE SET value = excluded.value, note = excluded.note, updated_at = excluded.updated_at",
        (goal_id, day, value, note, db.now()),
    )
    return {"goal_id": goal_id, "day": day, "value": value, "note": note}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def day_view(day: str) -> dict:
    """Goals with the value logged on `day` and progress toward their target (daily or that week)."""
    d = date.fromisoformat(day)
    ws, we = week_start(d), week_start(d) + timedelta(days=6)
    out = []
    for g in list_goals():
        log = db.one("SELECT value, note FROM logs WHERE goal_id = ? AND day = ?", (g["id"], day))
        week = db.one("SELECT COALESCE(SUM(value), 0) AS v FROM logs WHERE goal_id = ? AND day BETWEEN ? AND ?",
                      (g["id"], ws.isoformat(), we.isoformat()))
        value = log["value"] if log else 0
        progress = week["v"] if g["period"] == "weekly" else value
        out.append({**g, "value": value, "note": log["note"] if log else "", "progress": progress,
                    "met": progress >= g["target"], "pace": pace(g, d)})
    return {"day": day, "week_start": ws.isoformat(), "goals": out}


def burnup(g: dict, today: date) -> list[dict] | None:
    """Cumulative amount done per day from start_date to deadline, next to the straight-line plan."""
    p = pace(g, today)
    if not p:
        return None
    start, deadline = date.fromisoformat(p["start_date"]), date.fromisoformat(p["deadline"])
    span = max(1, (deadline - start).days + 1)
    rows = {r["day"]: r["value"] for r in db.query(
        "SELECT day, value FROM logs WHERE goal_id = ? AND day >= ? AND day <= ?", (g["id"], start.isoformat(), deadline.isoformat()))}
    out, cum = [], 0.0
    for i in range(span):
        d = start + timedelta(days=i)
        if d <= today:
            cum += rows.get(d.isoformat(), 0)
        out.append({"day": d.isoformat(), "actual": round(cum, 2) if d <= today else None,
                    "plan": round(p["total"] * (i + 1) / span, 2)})
    return out


# ---- stats for charts ----------------------------------------------------------
def stats(days: int = 84) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)
    span = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    goals = list_goals()
    result = []
    for g in goals:
        rows = {r["day"]: r["value"] for r in db.query(
            "SELECT day, value FROM logs WHERE goal_id = ? AND day >= ?", (g["id"], start.isoformat()))}
        daily = [{"day": d, "value": rows.get(d, 0)} for d in span]

        weeks: dict[str, float] = {}
        for item in daily:
            ws = week_start(date.fromisoformat(item["day"])).isoformat()
            weeks[ws] = weeks.get(ws, 0) + item["value"]
        weekly = [{"week": k, "value": v} for k, v in sorted(weeks.items())]

        if g["period"] == "daily":
            met = [x["value"] >= g["target"] for x in daily]
            unit_label = "day"
        else:
            met = [x["value"] >= g["target"] for x in weekly]
            unit_label = "week"
        best = cur = 0
        for m in met:
            cur = cur + 1 if m else 0
            best = max(best, cur)
        current, i = 0, len(met) - 1
        if i >= 0 and not met[i]:  # today / this week not done yet doesn't break the streak
            i -= 1
        while i >= 0 and met[i]:
            current, i = current + 1, i - 1
        window = met[-30:] if g["period"] == "daily" else met[-4:]
        result.append({
            "goal": g, "daily": daily, "weekly": weekly[-12:],
            "streak": {"current": current, "best": best, "unit": unit_label,
                       "rate": round(100 * sum(window) / max(1, len(window))), "window": "30 days" if g["period"] == "daily" else "4 weeks"},
            "total_30": sum(x["value"] for x in daily[-30:]),
            "pace": pace(g, today),
            "burnup": burnup(g, today),
        })
    return {"today": today.isoformat(), "goals": result}
