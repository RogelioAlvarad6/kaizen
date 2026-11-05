"""Starter workflows, created on first launch (only if the workflow id doesn't exist yet)."""
from __future__ import annotations

from . import db


def node(nid: str, block: str, x: int, y: int, label: str, **config) -> dict:
    return {"id": nid, "type": "block", "position": {"x": x, "y": y}, "data": {"blockType": block, "label": label, "config": config}}


def edge(src: str, dst: str, handle: str | None = None) -> dict:
    e = {"id": f"e-{src}-{dst}", "source": src, "target": dst}
    if handle:
        e["sourceHandle"] = handle
    return e


CHECKIN_SYSTEM = """You are the user's accountability coach for daily habits.
Goals: read daily, take the gym seriously (progressive overload), study for their current cert, build financial literacy.
1. Parse the check-in. Log EVERY item with habit_log (gym = 1 per session with exercises/sets/weights in the note;
   reading/study/finance = minutes, with book or topic in the note).
2. Call habit_summary(days=7) and get_goals.
3. Write the daily note with wiki_write to daily/{{today}}.md (mode append if it may already exist), formatted:
   ---
   type: daily
   date: {{today}}
   tags: [daily, checkin]
   ---
   # {{today}} check-in
   ## Logged
   ## Progress vs goals
   ## Coach notes
   Link related wiki pages where obvious (e.g. [[concepts/Progressive Overload]]).
4. Log it with wiki_log (verb "checkin").
Reply with a short summary: what was logged, goal progress, streaks, and one specific suggestion for tomorrow."""

NUDGE_PROMPT = """Here is my habit data:
{{habits_1}}

Is anything from TODAY still behind my daily goals (reading minutes, study minutes) or have I skipped the gym 3+ days?
If everything is on track, reply with exactly: NONE
Otherwise reply with ONE short, friendly, specific nudge (max 25 words), e.g. "15 min of reading left today - knock out a chapter before bed." """

WEEKLY_SYSTEM = """You write the user's weekly growth report. Be specific and honest, motivating but not fluffy.
Use the tools to read log.md (this week's wiki activity), the daily notes in daily/ from this week, and index.md.
Goals: gym consistency + progressive overload, daily reading, studying for their current cert (Security+), financial literacy, dev skills.
Output a markdown note with YAML frontmatter (type: report, tags: [weekly-report], week: {{week}}) and sections:
# Weekly Growth Report - {{week}}
## Scorecard  (table: habit | goal | actual | status)
## What I learned  (link wiki pages that were created/updated this week with [[wikilinks]])
## Wins
## Gaps & patterns  (missed days, knowledge gaps you notice in the wiki)
## Next week  (3-5 concrete actions, include 2-3 suggested things to read/ingest)"""

SEEDS = [
    {
        "id": "wiki-ingest",
        "name": "Wiki: Ingest new sources",
        "description": "Drop an article/PDF in AI-Wiki/raw → Claude writes linked wiki pages, updates index & log, then notifies you.",
        "graph": {
            "nodes": [
                node("folder_1", "trigger.folder", 40, 60, "New file in raw/"),
                node("manual_1", "trigger.manual", 40, 220, "Run manually (all new files)"),
                node("ingest_1", "wiki.ingest", 340, 140, "Ingest into wiki", model="claude-opus-5-5", effort="medium", max_files=5, path_template=""),
                node("notify_1", "util.notify", 660, 140, "Notify", title="Wiki updated", message="Ingest finished. Open Obsidian to see the new pages."),
            ],
            "edges": [edge("folder_1", "ingest_1"), edge("manual_1", "ingest_1"), edge("ingest_1", "notify_1")],
        },
    },
    {
        "id": "wiki-ask",
        "name": "Wiki: Ask my wiki",
        "description": "Ask a question; Claude answers from your wiki with [[citations]] and files good answers back.",
        "graph": {
            "nodes": [
                node("manual_1", "trigger.manual", 40, 60, "Question", default_input="What have I learned about Security+ so far?"),
                node("chat_1", "trigger.chat", 40, 220, "From chat"),
                node("query_1", "wiki.query", 340, 140, "Answer from wiki", model="claude-opus-5-5", effort="low", question="{{input}}", file_back=True),
            ],
            "edges": [edge("manual_1", "query_1"), edge("chat_1", "query_1")],
        },
    },
    {
        "id": "wiki-lint",
        "name": "Wiki: Weekly lint",
        "description": "Every Saturday morning: find contradictions, orphan pages and missing links; writes a report.",
        "enabled": True,
        "graph": {
            "nodes": [
                node("sched_1", "trigger.schedule", 40, 60, "Saturdays 10am", cron="0 10 * * sat"),
                node("manual_1", "trigger.manual", 40, 220, "Run now"),
                node("lint_1", "wiki.lint", 340, 140, "Lint wiki", model="claude-opus-5-5", effort="medium"),
            ],
            "edges": [edge("sched_1", "lint_1"), edge("manual_1", "lint_1")],
        },
    },
    {
        "id": "daily-checkin",
        "name": "Daily habit check-in",
        "description": "Type how your day went (gym, reading, study). Claude logs habits, writes daily/<date>.md in Obsidian, and coaches you.",
        "graph": {
            "nodes": [
                node("manual_1", "trigger.manual", 40, 60, "Check-in text",
                     default_input="Push day: bench 3x8 185, OHP 3x8 95. Read Atomic Habits 25 min. Studied Security+ domain 2 for 40 min."),
                node("chat_1", "trigger.chat", 40, 220, "From chat"),
                node("agent_1", "ai.agent", 340, 140, "Coach + logger", model="claude-opus-5-5", effort="low",
                     system=CHECKIN_SYSTEM, prompt="My check-in for today:\n{{input}}", tools=["habits", "wiki_read", "wiki_write"], max_turns=15),
            ],
            "edges": [edge("manual_1", "agent_1"), edge("chat_1", "agent_1")],
        },
    },
    {
        "id": "evening-nudge",
        "name": "Evening accountability nudge",
        "description": "8:30pm daily: if you're behind on today's goals, you get a Windows notification nudge.",
        "graph": {
            "nodes": [
                node("sched_1", "trigger.schedule", 40, 140, "8:30pm daily", cron="30 20 * * *"),
                node("habits_1", "habits.summary", 300, 140, "Today's habits", days=7),
                node("agent_1", "ai.agent", 560, 140, "Decide nudge", model="claude-haiku-5-5", effort="low",
                     system="You are a concise accountability coach.", prompt=NUDGE_PROMPT, tools=[], max_turns=2),
                node("cond_1", "logic.condition", 820, 140, "Needs nudge?", input="{{agent_1}}", mode="not_contains", value="NONE"),
                node("notify_1", "util.notify", 1080, 80, "Nudge", title="Habit check", message="{{agent_1}}"),
            ],
            "edges": [edge("sched_1", "habits_1"), edge("habits_1", "agent_1"), edge("agent_1", "cond_1"), edge("cond_1", "notify_1", "true")],
        },
    },
    {
        "id": "weekly-report",
        "name": "Weekly growth report",
        "description": "Sundays 6pm: habits + learning + cert progress → reports/weekly-<week>.md in Obsidian, then a notification.",
        "graph": {
            "nodes": [
                node("sched_1", "trigger.schedule", 40, 60, "Sundays 6pm", cron="0 18 * * sun"),
                node("manual_1", "trigger.manual", 40, 220, "Run now"),
                node("habits_1", "habits.summary", 300, 140, "Last 7 days", days=7),
                node("agent_1", "ai.agent", 560, 140, "Write report", model="claude-opus-5-5", effort="medium", system=WEEKLY_SYSTEM,
                     prompt="Habit data for this week:\n{{habits_1}}\n\nWrite my weekly growth report for {{week}}.",
                     tools=["wiki_read", "habits"], max_turns=20),
                node("note_1", "wiki.note", 820, 140, "Save to Obsidian", path="reports/weekly-{{week}}.md", content="{{agent_1}}", mode="overwrite", log_verb="report"),
                node("notify_1", "util.notify", 1080, 140, "Notify", title="Weekly report ready", message="Your weekly growth report for {{week}} is in Obsidian → AI-Wiki/reports."),
            ],
            "edges": [edge("sched_1", "habits_1"), edge("manual_1", "habits_1"), edge("habits_1", "agent_1"), edge("agent_1", "note_1"), edge("note_1", "notify_1")],
        },
    },
]


def seed() -> None:
    for wf in SEEDS:
        if not db.get_workflow(wf["id"]):
            db.save_workflow(wf)
