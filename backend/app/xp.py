"""Points, levels and badges - all derived from the logs, so editing or backfilling a day re-scores it.

Scoring
  daily goal met ............ +10   (partial progress +5)
  perfect day ............... +20   (every active daily goal met)
  weekly goal met ........... +50   (+3 for each day you logged something toward it)
  daily streak hits 7/30/100  +50 / +200 / +1000
  weekly streak hits 4/12 ... +100 / +400
  deadline goal completed ... +500  (e.g. passing an exam)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from . import db

XP = {"met": 10, "partial": 5, "perfect_day": 20, "week_met": 50, "week_day": 3, "completed": 500}
DAILY_STREAK_BONUS = {7: 50, 30: 200, 100: 1000}
WEEKLY_STREAK_BONUS = {4: 100, 12: 400}

TITLES = [(1, "Recruit"), (3, "Apprentice"), (5, "Operator"), (8, "Analyst"), (11, "Specialist"), (15, "Expert"), (20, "Master")]

BADGES = [
    ("first_step", "First step", "Log anything for the first time"),
    ("perfect_day", "Perfect day", "Hit every daily goal in one day"),
    ("streak_7", "One week strong", "7-day streak on a daily goal"),
    ("streak_30", "Habit formed", "30-day streak on a daily goal"),
    ("streak_100", "Unbreakable", "100-day streak on a daily goal"),
    ("perfect_week", "Perfect week", "Every daily and weekly goal met, Mon-Sun"),
    ("consistent", "Consistent", "Meet a weekly goal 4 weeks in a row"),
    ("big_week", "Big week", "Earn 400 XP in a single week"),
    ("level_5", "Operator", "Reach level 5"),
    ("level_10", "Analyst", "Reach level 10"),
    ("certified", "Certified", "Complete a deadline goal (pass an exam)"),
]


def level_need(n: int) -> int:
    """XP needed to go from level n to n+1."""
    return 100 + 50 * (n - 1)


def level_for(xp: float) -> dict:
    n, floor = 1, 0
    while xp >= floor + level_need(n):
        floor += level_need(n)
        n += 1
    title = [t for lvl, t in TITLES if n >= lvl][-1]
    return {"level": n, "title": title, "level_floor": floor, "next_at": floor + level_need(n),
            "into_level": xp - floor, "level_size": level_need(n)}


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def compute(today: date | None = None) -> dict:
    today = today or date.today()
    goals = db.query("SELECT * FROM goals ORDER BY id")
    logs: dict[int, dict[str, float]] = defaultdict(dict)
    for r in db.query("SELECT goal_id, day, value FROM logs WHERE value > 0"):
        logs[r["goal_id"]][r["day"]] = r["value"]

    events: list[dict] = []

    def add(day: date, xp: int, reason: str, goal: str = "") -> None:
        events.append({"day": day.isoformat(), "xp": xp, "reason": reason, "goal": goal})

    def goal_start(g: dict) -> date:
        days = [_d(x) for x in logs[g["id"]]]
        created = _d(g["created_at"]) if g.get("created_at") else today
        return min([created, *days])

    # ---- daily goals: met / partial / streak bonuses
    met_by_day: dict[str, set[int]] = defaultdict(set)
    daily = [g for g in goals if g["period"] == "daily"]
    for g in daily:
        target = g["target"] if g["kind"] == "number" else 1
        d, run = goal_start(g), 0
        while d <= today:
            v = logs[g["id"]].get(d.isoformat(), 0)
            if v >= target:
                add(d, XP["met"], "goal met", g["name"])
                met_by_day[d.isoformat()].add(g["id"])
                run += 1
                if run in DAILY_STREAK_BONUS:
                    add(d, DAILY_STREAK_BONUS[run], f"{run}-day streak", g["name"])
            else:
                if v > 0:
                    add(d, XP["partial"], "partial progress", g["name"])
                if d != today:  # today isn't over yet
                    run = 0
            d += timedelta(days=1)

    # ---- perfect days: every non-archived daily goal that existed that day was met
    active_daily = [g for g in daily if not g["archived"]]
    perfect_days: set[str] = set()
    if active_daily:
        first = min(goal_start(g) for g in active_daily)
        d = first
        while d <= today:
            existing = [g for g in active_daily if goal_start(g) <= d]
            if existing and all(g["id"] in met_by_day[d.isoformat()] for g in existing):
                add(d, XP["perfect_day"], "perfect day")
                perfect_days.add(d.isoformat())
            d += timedelta(days=1)

    # ---- weekly goals: met per Mon-Sun week, days of effort, week streaks
    weekly = [g for g in goals if g["period"] == "weekly"]
    weeks_met: dict[str, set[int]] = defaultdict(set)
    for g in weekly:
        wk, run = week_start(goal_start(g)), 0
        while wk <= today:
            days = [wk + timedelta(days=i) for i in range(7)]
            vals = [logs[g["id"]].get(x.isoformat(), 0) for x in days if x <= today]
            for x in days:
                if x <= today and logs[g["id"]].get(x.isoformat(), 0) > 0:
                    add(x, XP["week_day"], "showed up", g["name"])
            total = sum(vals)
            if total >= g["target"]:
                # credit on the day the target was crossed
                cum, hit = 0.0, wk
                for x in days:
                    cum += logs[g["id"]].get(x.isoformat(), 0)
                    if cum >= g["target"]:
                        hit = x
                        break
                add(hit, XP["week_met"], "weekly goal met", g["name"])
                weeks_met[wk.isoformat()].add(g["id"])
                run += 1
                if run in WEEKLY_STREAK_BONUS:
                    add(hit, WEEKLY_STREAK_BONUS[run], f"{run}-week streak", g["name"])
            elif wk != week_start(today):
                run = 0
            wk += timedelta(days=7)

    # ---- completed deadline goals (e.g. passed the exam)
    for g in goals:
        if g.get("completed_at"):
            add(_d(g["completed_at"]), XP["completed"], "completed", g["name"])

    events.sort(key=lambda e: e["day"])
    total = sum(e["xp"] for e in events)

    # ---- per-day and per-week totals
    by_day: dict[str, int] = defaultdict(int)
    for e in events:
        by_day[e["day"]] += e["xp"]
    by_week: dict[str, int] = defaultdict(int)
    for day, xp in by_day.items():
        by_week[week_start(_d(day)).isoformat()] += xp
    this_wk = week_start(today)
    last_wk = this_wk - timedelta(days=7)

    # ---- badges (with the date each was first earned)
    earned: dict[str, str] = {}

    def earn(key: str, day: str) -> None:
        if key not in earned or day < earned[key]:
            earned[key] = day

    if events:
        first_log = min(day for g in logs.values() for day in g)
        earn("first_step", first_log)
    for day in sorted(perfect_days):
        earn("perfect_day", day)
    for e in events:
        if e["reason"] == "7-day streak":
            earn("streak_7", e["day"])
        elif e["reason"] == "30-day streak":
            earn("streak_30", e["day"])
        elif e["reason"] == "100-day streak":
            earn("streak_100", e["day"])
        elif e["reason"] == "4-week streak":
            earn("consistent", e["day"])
        elif e["reason"] == "completed":
            earn("certified", e["day"])
    active_weekly = [g for g in weekly if not g["archived"]]
    for wk in sorted({week_start(_d(d)) for d in perfect_days}):
        days = [(wk + timedelta(days=i)).isoformat() for i in range(7)]
        weekly_ok = all(g["id"] in weeks_met[wk.isoformat()] for g in active_weekly)
        if all(d in perfect_days for d in days) and weekly_ok:
            earn("perfect_week", days[-1])
    for wk, xp in sorted(by_week.items()):
        if xp >= 400:
            earn("big_week", wk)
    cum = 0
    for day in sorted(by_day):
        cum += by_day[day]
        lvl = level_for(cum)["level"]
        if lvl >= 5:
            earn("level_5", day)
        if lvl >= 10:
            earn("level_10", day)

    lvl = level_for(total)
    max_daily = XP["met"] * len(active_daily) + (XP["perfect_day"] if active_daily else 0)
    last30 = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    return {
        "xp": total, **lvl,
        "today": by_day.get(today.isoformat(), 0),
        "this_week": by_week.get(this_wk.isoformat(), 0),
        "last_week": by_week.get(last_wk.isoformat(), 0),
        "best_week": max(by_week.values(), default=0),
        "perfect_day_xp": max_daily,
        "daily": [{"day": d, "xp": by_day.get(d, 0)} for d in last30],
        "badges": [{"key": k, "name": n, "desc": desc, "earned_on": earned.get(k)} for k, n, desc in BADGES],
        "recent": list(reversed(events))[:15],
        "rules": {**XP, "daily_streak": DAILY_STREAK_BONUS, "weekly_streak": WEEKLY_STREAK_BONUS},
    }
