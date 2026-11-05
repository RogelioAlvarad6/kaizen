"""Discord nudges for Kaizen: speak up only when it matters.

  behind      ~5pm   - daily goals still open today (+ cert pace if behind)        only if something is open
  streak      ~10:30 - a streak of 3+ days ends at midnight unless you log         only if a streak is at risk
  weekly      Sun    - scorecard: XP vs last week, goals hit, streaks, cert pace   always
  levelups    5 min  - new level or badge since the last announcement

Config (env, in ~/docker/sims-tracker/.env on the Pi):
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   (required)
  DISCORD_USER_ID=123456789012345678                          (optional: @mention you so Discord pings)
  KAIZEN_TZ=America/Chicago                                   (optional, default America/Chicago)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, tracker, xp

log = logging.getLogger("kaizen.nudges")
TZ = ZoneInfo(os.getenv("KAIZEN_TZ", "America/Chicago"))
APP_URL = os.getenv("KAIZEN_URL", "http://localhost:8000")  # shown in Discord messages
RED, INK, GREEN = 0xE30613, 0x111111, 0x2E7D32

SETTINGS = {  # key: default
    "notify_enabled": "true",
    "notify_behind_at": "17:00",
    "notify_streak_at": "22:30",
    "notify_weekly_day": "sun",
    "notify_weekly_at": "19:00",
}

scheduler = BackgroundScheduler(timezone=TZ)


# ---- sending ---------------------------------------------------------------------
def webhook_url() -> str:
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()


def configured() -> bool:
    u = webhook_url()
    return u.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/", "https://ptb.discord.com/api/webhooks/", "https://canary.discord.com/api/webhooks/"))


def send(title: str, lines: list[str], color: int = INK, mention: bool = True) -> None:
    if not configured():
        raise RuntimeError("Discord webhook not configured (DISCORD_WEBHOOK_URL in the Pi's .env)")
    uid = os.getenv("DISCORD_USER_ID", "").strip()
    payload = {
        "username": "Kaizen",
        "content": f"<@{uid}>" if (uid and mention) else "",
        "allowed_mentions": {"users": [uid] if uid else []},
        "embeds": [{
            "title": title[:256],
            "description": "\n".join(lines)[:4000],
            "color": color,
            # no "url": Discord rejects non-public links like http://my-pi:8100
            "footer": {"text": f"Kaizen · 改善 · {APP_URL}"},
        }],
    }
    req = urllib.request.Request(webhook_url(), data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Kaizen-homelab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status >= 300:
                raise RuntimeError(f"Discord returned {r.status}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Discord returned {e.code}: {e.read()[:200].decode(errors='replace')}") from e


# ---- helpers ---------------------------------------------------------------------
def today() -> date:
    return datetime.now(TZ).date()


def amt(v: float, unit: str) -> str:
    if unit == "min":
        m = int(round(v))
        return f"{m}m" if m < 60 else f"{m // 60}h{f' {m % 60}m' if m % 60 else ''}"
    return f"{v:g} {unit}"


def pace_line(g: dict) -> str | None:
    p = g.get("pace")
    if not p or p["status"] in ("completed", "done"):
        return None
    if p["status"] == "overdue":
        return f"⏰ **{g['name']}** is past its deadline ({amt(p['remaining'], g['unit'])} left)"
    status = f"behind by **{amt(p['gap_per_day'], g['unit'])}/day**" if p["status"] == "behind" else "on pace ✓"
    return f"🎯 **{g['name']}** · {p['days_left']} days left · need {amt(p['need_per_day'], g['unit'])}/day · {status}"


# ---- messages (return None when there's nothing worth saying) ----------------------
def build_behind(force: bool = False) -> tuple[str, list[str], int] | None:
    d = today()
    view = tracker.day_view(d.isoformat())["goals"]
    open_daily = [g for g in view if g["period"] == "daily" and not g["met"]]
    if not open_daily and not force:
        return None
    days_left_in_week = 7 - d.weekday()
    lines = []
    for g in open_daily:
        if g["kind"] == "check":
            lines.append(f"• **{g['name']}** - not done yet")
        else:
            lines.append(f"• **{g['name']}** - {amt(g['value'], g['unit'])} / {amt(g['target'], g['unit'])} "
                         f"({amt(g['target'] - g['value'], g['unit'])} to go)")
    for g in view:
        if g["period"] == "weekly" and not g["met"]:
            left = g["target"] - g["progress"]
            lines.append(f"• **{g['name']}** this week - {g['progress']:g} / {g['target']:g} {g['unit']} "
                         f"({left:g} to go, {days_left_in_week} day{'s' if days_left_in_week != 1 else ''} left)")
    pls = [pl for g in view if (pl := pace_line(g))]
    if pls:
        lines += ["", *pls]
    daily_n = len([g for g in view if g["period"] == "daily"])
    if open_daily:
        bonus = 10 * len(open_daily) + (20 if daily_n and len(open_daily) <= daily_n else 0)
        lines += ["", f"Close them out for **+{bonus} XP** (perfect day included)."]
    else:
        lines = ["Every daily goal is done today. Nice. ✓", *lines]
    title = f"{len(open_daily)} goal{'s' if len(open_daily) != 1 else ''} left today" if open_daily else "You're on track today"
    return title, lines, RED if open_daily else GREEN


def build_streak(force: bool = False) -> tuple[str, list[str], int] | None:
    d = today()
    stats = {s["goal"]["id"]: s for s in tracker.stats(365)["goals"]}
    view = tracker.day_view(d.isoformat())["goals"]
    lines = []
    for g in view:
        s = stats.get(g["id"])
        if not s or g["period"] != "daily" or g["met"]:
            continue
        run = s["streak"]["current"]  # today not met -> this is the streak through yesterday
        if run >= 3:
            todo = "mark it done" if g["kind"] == "check" else f"{amt(g['target'] - g['value'], g['unit'])} to go"
            lines.append(f"🔥 **{g['name']}** - your **{run}-day streak** ends at midnight ({todo})")
    if not lines and not force:
        return None
    if not lines:
        lines = ["No streaks at risk tonight. ✓"]
    return ("Streak at risk" if len(lines) == 1 else f"{len(lines)} streaks at risk"), lines, RED


def build_weekly(force: bool = True) -> tuple[str, list[str], int]:
    d = today()
    wk = d - timedelta(days=d.weekday())
    x = xp.compute(d)
    stats = tracker.stats(365)["goals"]
    lines = []
    beat = x["this_week"] - x["last_week"]
    verdict = f"beat last week by **{beat}** 💪" if beat > 0 else ("tied last week" if beat == 0 else f"**{-beat}** short of last week")
    lines.append(f"**{x['this_week']} XP** this week ({verdict}) · best week ever: {x['best_week']}")
    lines.append(f"Level **{x['level']} · {x['title']}** - {int(x['into_level'])}/{x['level_size']} XP to level {x['level'] + 1}")
    lines.append("")
    for s in stats:
        g = s["goal"]
        week_days = [v for v in s["daily"] if v["day"] >= wk.isoformat()]
        if g["period"] == "daily":
            target = g["target"] if g["kind"] == "number" else 1
            hit = sum(1 for v in week_days if v["value"] >= target)
            total = sum(v["value"] for v in week_days)
            extra = f" · {amt(total, g['unit'])} total" if g["kind"] == "number" else ""
            lines.append(f"• **{g['name']}** - goal hit {hit}/{len(week_days)} days{extra} · streak {s['streak']['current']}d")
        else:
            total = sum(v["value"] for v in week_days)
            mark = "✓" if total >= g["target"] else "✗"
            lines.append(f"• **{g['name']}** - {total:g}/{g['target']:g} {g['unit']} {mark} · {s['streak']['current']}-week streak")
    pls = [pl for s in stats if (pl := pace_line({**s["goal"], "pace": s["pace"]}))]
    if pls:
        lines += ["", *pls]
    new_badges = [b["name"] for b in x["badges"] if b["earned_on"] and b["earned_on"] >= wk.isoformat()]
    if new_badges:
        lines += ["", "🏅 Badges this week: " + ", ".join(new_badges)]
    lines += ["", "New week tomorrow - beat this score."]
    return f"Week of {wk.strftime('%b %d').replace(' 0', ' ')} - scorecard", lines, INK


def check_levelups(announce: bool = True) -> list[str]:
    """Announce new levels/badges since the last check. First run only records the baseline."""
    x = xp.compute(today())
    s = db.get_settings()
    earned = sorted(b["key"] for b in x["badges"] if b["earned_on"])
    if "announced_level" not in s:
        db.set_setting("announced_level", str(x["level"]))
        db.set_setting("announced_badges", ",".join(earned))
        return []
    msgs = []
    prev_level = int(s.get("announced_level") or 1)
    prev_badges = set(filter(None, (s.get("announced_badges") or "").split(",")))
    if x["level"] > prev_level:
        msgs.append(f"⬆️ **Level {x['level']} · {x['title']}** reached ({x['xp']:,} XP total)")
    for b in x["badges"]:
        if b["earned_on"] and b["key"] not in prev_badges:
            msgs.append(f"🏅 Badge unlocked: **{b['name']}** - {b['desc']}")
    if msgs and announce and configured():
        send("Level up!" if x["level"] > prev_level else "New badge", msgs, RED, mention=False)
    db.set_setting("announced_level", str(max(x["level"], prev_level)))
    db.set_setting("announced_badges", ",".join(sorted(prev_badges | set(earned))))
    return msgs


BUILDERS = {"behind": build_behind, "streak": build_streak, "weekly": build_weekly}


def run(kind: str, force: bool = False) -> str:
    """Build and send one message kind. Returns what happened (for logs and the test buttons)."""
    if kind == "levelups":
        msgs = check_levelups()
        return f"announced {len(msgs)}" if msgs else "nothing new"
    msg = BUILDERS[kind](force=force)  # type: ignore[operator]
    if msg is None:
        return "nothing to send (you're on track)"
    send(*msg)
    return "sent"


def _job(kind: str) -> None:
    try:
        if db.get_settings().get("notify_enabled", "true") != "true" or not configured():
            return
        log.info("nudge %s: %s", kind, run(kind))
    except Exception as e:  # a failed nudge must never take the app down
        log.error("nudge %s failed: %s", kind, e)


# ---- schedule ----------------------------------------------------------------------
def settings() -> dict:
    s = db.get_settings()
    return {k: s.get(k, v) for k, v in SETTINGS.items()}


def _hm(v: str, fallback: str) -> tuple[int, int]:
    try:
        h, m = (int(x) for x in v.split(":"))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except ValueError:
        pass
    h, m = fallback.split(":")
    return int(h), int(m)


def reload() -> None:
    s = settings()
    scheduler.remove_all_jobs()
    bh, bm = _hm(s["notify_behind_at"], SETTINGS["notify_behind_at"])
    sh, sm = _hm(s["notify_streak_at"], SETTINGS["notify_streak_at"])
    wh, wm = _hm(s["notify_weekly_at"], SETTINGS["notify_weekly_at"])
    day = s["notify_weekly_day"] if s["notify_weekly_day"] in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") else "sun"
    scheduler.add_job(_job, CronTrigger(hour=bh, minute=bm, timezone=TZ), args=["behind"], id="behind", misfire_grace_time=1800)
    scheduler.add_job(_job, CronTrigger(hour=sh, minute=sm, timezone=TZ), args=["streak"], id="streak", misfire_grace_time=1800)
    scheduler.add_job(_job, CronTrigger(day_of_week=day, hour=wh, minute=wm, timezone=TZ), args=["weekly"], id="weekly", misfire_grace_time=3600)
    scheduler.add_job(_job, "interval", minutes=5, args=["levelups"], id="levelups")


def next_runs() -> dict:
    return {j.id: j.next_run_time.isoformat(timespec="minutes") if j.next_run_time else None for j in scheduler.get_jobs()}


def start() -> None:
    for k, v in SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    check_levelups(announce=False)  # record baseline so old achievements aren't re-announced
    if not scheduler.running:
        scheduler.start()
    reload()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
