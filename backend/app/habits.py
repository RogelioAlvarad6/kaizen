"""Habit tracking (gym, reading, study, ...) stored in SQLite."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from . import db

KINDS = ["gym", "reading", "study", "finance", "other"]
DEFAULT_UNITS = {"gym": "session", "reading": "min", "study": "min", "finance": "min", "other": ""}


def log(kind: str, value: float = 1, unit: str = "", note: str = "", day: str | None = None) -> dict:
    kind = (kind or "other").strip().lower()
    day = day or date.today().isoformat()
    unit = unit or DEFAULT_UNITS.get(kind, "")
    hid = db.execute(
        "INSERT INTO habits(day, kind, value, unit, note, created_at) VALUES (?,?,?,?,?,?)",
        (day, kind, float(value or 0), unit, note or "", db.now()),
    )
    return {"id": hid, "day": day, "kind": kind, "value": value, "unit": unit, "note": note}


def entries(days: int = 14) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    return db.query("SELECT * FROM habits WHERE day >= ? ORDER BY day DESC, id DESC", (start,))


def delete(hid: int) -> None:
    db.execute("DELETE FROM habits WHERE id = ?", (hid,))


def goals() -> dict:
    s = db.get_settings()
    return {
        "reading_goal_minutes": float(s.get("reading_goal_minutes", 30)),
        "gym_goal_per_week": float(s.get("gym_goal_per_week", 4)),
        "study_goal_minutes": float(s.get("study_goal_minutes", 45)),
        "current_cert": s.get("current_cert", "CompTIA Security+"),
    }


def daily_totals(days: int = 14) -> list[dict]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in entries(days):
        totals[e["day"]][e["kind"]] += e["value"]
    out = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        out.append({"day": d, **{k: totals[d].get(k, 0) for k in KINDS}})
    return out


def streak(kind: str, minimum: float) -> int:
    """Consecutive days (ending today, or yesterday if today isn't logged yet) meeting `minimum`."""
    rows = daily_totals(120)
    count, started = 0, False
    for i, r in enumerate(rows):
        ok = r[kind] >= minimum
        if i == 0 and not ok:
            continue  # today not done yet doesn't break the streak
        if ok:
            count += 1
            started = True
        elif started or i > 0:
            break
    return count


def progress(days: int = 84) -> dict:
    """Everything the Today/Progress charts need, oldest day first."""
    g = goals()
    rows = list(reversed(daily_totals(days)))
    targets = {"reading": g["reading_goal_minutes"], "study": g["study_goal_minutes"], "gym": 1}

    def streaks(kind: str) -> dict:
        met = [r[kind] >= targets[kind] for r in rows]
        best = cur = 0
        for m in met:
            cur = cur + 1 if m else 0
            best = max(best, cur)
        # current streak: ending today, or yesterday if today isn't done yet
        current, i = 0, len(met) - 1
        if i >= 0 and not met[i]:
            i -= 1
        while i >= 0 and met[i]:
            current, i = current + 1, i - 1
        last30 = met[-30:]
        return {"current": current, "best": best, "rate30": round(100 * sum(last30) / max(1, len(last30)))}

    # gym sessions per ISO week (Mon-Sun), last 12 weeks
    weeks: dict[str, float] = {}
    for r in rows:
        d = date.fromisoformat(r["day"])
        monday = (d - timedelta(days=d.weekday())).isoformat()
        weeks[monday] = weeks.get(monday, 0) + r["gym"]
    gym_weeks = [{"week": k, "sessions": v} for k, v in sorted(weeks.items())][-12:]

    return {"days": rows, "goals": g, "targets": targets,
            "streaks": {k: streaks(k) for k in ("reading", "study", "gym")}, "gym_weeks": gym_weeks}


def summary_text(days: int = 7) -> str:
    g = goals()
    rows = daily_totals(days)
    gym_sessions = sum(r["gym"] for r in rows)
    read_total = sum(r["reading"] for r in rows)
    study_total = sum(r["study"] for r in rows)
    today = rows[0]
    lines = [
        f"Habit summary for the last {days} day(s) (today = {today['day']}):",
        f"- Goals: read {g['reading_goal_minutes']:.0f} min/day, gym {g['gym_goal_per_week']:.0f}x/week, study {g['study_goal_minutes']:.0f} min/day ({g['current_cert']}).",
        f"- Today: reading {today['reading']:.0f} min, gym {today['gym']:.0f} session(s), study {today['study']:.0f} min.",
        f"- Period totals: reading {read_total:.0f} min (avg {read_total / days:.0f}/day), gym {gym_sessions:.0f} session(s), study {study_total:.0f} min.",
        f"- Days reading goal met: {sum(1 for r in rows if r['reading'] >= g['reading_goal_minutes'])}/{days}.",
        f"- Reading streak: {streak('reading', g['reading_goal_minutes'])} day(s). Study streak: {streak('study', 1)} day(s).",
        "- Daily breakdown (day: reading min / gym / study min):",
    ]
    for r in rows:
        lines.append(f"  - {r['day']}: {r['reading']:.0f} / {r['gym']:.0f} / {r['study']:.0f}")
    notes = [e for e in entries(days) if e["note"]]
    if notes:
        lines.append("- Notes:")
        for e in notes[:25]:
            lines.append(f"  - {e['day']} [{e['kind']}] {e['note']}")
    return "\n".join(lines)
