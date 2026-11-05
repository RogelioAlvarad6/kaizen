# Kaizen 改善

**A self-hosted daily discipline tracker: personal and professional goals, streaks, levels, certification deadlines, and Discord nudges.** Kaizen means "continuous improvement", 1% better every day.

It runs on a Raspberry Pi (or any Linux box with Docker), is reached privately over Tailscale, and is designed around one rule: logging should take seconds, and the app should reach out to you only when it matters.

## Features

- **Today**: log every goal with −/+ buttons or a checkbox, add notes, and backfill past days. A level strip, certification countdowns, and a 7-day grid show how the day is going.
- **Goals**: personal or professional, daily or weekly, an amount (minutes, sessions, pages…) or yes/no. Archive without losing history.
- **Certification deadlines**: set an exam date and total hours. Kaizen shows days left, the pace you need per day, your 14-day average, and whether you're ahead or behind, plus a burn-up chart.
- **Points & levels**: XP is derived from your logs, so fixing a past day re-scores it. Levels go Recruit → Apprentice → Operator → Analyst → Specialist → Expert → Master, with 11 badges.
- **Progress**: streaks, 12-week consistency heatmaps, goal-line bar charts, and a daily discipline chart.
- **Discord nudges** (webhook), sent only when they matter:
  - ~5 PM: goals still open today (+ cert pace)
  - ~10:30 PM: a 3+ day streak ends at midnight
  - Sunday: weekly scorecard vs. last week
  - Level-ups and new badges

### XP rules
| Event | XP |
|---|---|
| Daily goal met (partial) | +10 (+5) |
| Perfect day: every daily goal met | +20 |
| Weekly goal met (each day you show up) | +50 (+3) |
| Streak 7 / 30 / 100 days | +50 / +200 / +1000 |
| Weekly streak 4 / 12 weeks | +100 / +400 |
| Complete a deadline goal (pass the exam) | +500 |

## Stack

- **Backend:** Python 3.12, FastAPI, SQLite, APScheduler
- **Frontend:** React 18 + TypeScript (Vite), hand-written SVG charts, Swiss/minimal design
- **Deploy:** Docker Compose on the server, bound to localhost + a private (Tailscale) IP only. Kaizen has no login, so never expose it publicly.

```
backend/app/
  main.py        FastAPI app + API routes
  tracker.py     goals, daily logs, stats, deadline pace & burn-up
  xp.py          XP, levels, badges (computed from logs)
  nudges.py      Discord webhook messages + schedules
frontend/src/    React app (pages: Today, Progress, Goals)
deploy/          Dockerfile, docker-compose.yml, Pi backup & health scripts
deploy.ps1       build locally → upload → docker compose up on the server
```

## Run locally (Windows)

Requires Python 3.12+ and Node 20+.

```powershell
.\start.cmd          # first run creates backend\.venv, installs packages, opens http://localhost:5173
```

Settings go in `backend/.env` (copy `backend/.env.example`).

## Deploy to a Raspberry Pi / Linux server

1. On the server: Docker with the compose plugin, and a folder for the data (default `/mnt/data1/sims-tracker`, see `deploy/docker-compose.yml`).
2. Create `~/docker/sims-tracker/.env` on the server:
   ```
   KAIZEN_BIND_IP=100.x.y.z                 # e.g. the server's Tailscale IP
   KAIZEN_URL=http://your-server:8100       # shown in Discord messages
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # optional
   DISCORD_USER_ID=123456789012345678       # optional, to get @mentioned
   KAIZEN_TZ=America/Chicago                # optional
   ```
3. From this folder on your PC:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\deploy.ps1 -Target user@your-server
   ```
   (or put `user@your-server` in a git-ignored `.deploy-target` file). Then open `http://your-server:8100`.

## Homelab ops scripts (optional)

`deploy.ps1` also installs two scripts on the server:

- **`~/bin/nightly-backup.sh`**: backs up the Kaizen DB (SQLite online backup), a Minecraft world (paused saves via RCON), and `~/docker` configs to a second drive. Keeps 30/7/30 days.
- **`~/bin/pi-health.sh`**: every 2 minutes, checks that data drives are mounted, writable, and error-free, that disks are under 90%, and that the Minecraft world is still saving. If saves stop, it warns players in-game. Reports to **Uptime Kuma** push monitors.

Schedule them with cron (`crontab -e`):
```
0 3 * * *   $HOME/bin/nightly-backup.sh >/dev/null 2>&1
*/2 * * * * $HOME/bin/pi-health.sh >/dev/null 2>&1
```
Push URLs go in `~/.config/pi-health.env` (`KUMA_PUSH_STORAGE`, `KUMA_PUSH_MINECRAFT`, `KUMA_PUSH_BACKUP`). Run `~/bin/pi-health.sh -v` to see the current status.

## Parked: AI features

Kaizen started as an AI workflow canvas (Claude agents, an Obsidian "LLM wiki", chat). That code is still in `backend/app` (`engine.py`, `blocks.py`, `chat.py`, `wiki.py`…) and `frontend/src/pages` (Chat, Editor, Runs, Workflows), but it's switched off: no routes in the UI, and `ENABLE_AI_AUTOMATIONS=false`. Kaizen makes no AI calls and needs no API key.
