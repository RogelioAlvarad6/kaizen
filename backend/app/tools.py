"""Tools that agents can call, grouped so each agent block picks only what it needs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from . import habits, wiki


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., str]

    def definition(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _wiki_search(query: str, limit: int = 8) -> str:
    hits = wiki.search(query, limit)
    return json.dumps(hits, ensure_ascii=False) if hits else "No matching pages."


def _wiki_list(folder: str = "wiki") -> str:
    files = wiki.list_files(folder)
    return "\n".join(files) if files else f"(no files in {folder})"


def _wiki_write(path: str, content: str, mode: str = "overwrite") -> str:
    return f"Wrote {wiki.write(path, content, mode)}"


def _wiki_log(verb: str, text: str) -> str:
    wiki.append_log(verb, text)
    return "Logged."


def _habit_log(kind: str, value: float = 1, unit: str = "", note: str = "", day: str = "") -> str:
    return json.dumps(habits.log(kind, value, unit, note, day or None))


def _habit_summary(days: int = 7) -> str:
    return habits.summary_text(max(1, min(int(days), 90)))


def _goals() -> str:
    return json.dumps(habits.goals())


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("wiki_search", "Keyword search across the wiki (wiki/, daily/, reports/). Returns paths with snippets. Use before creating pages to avoid duplicates.",
         _obj({"query": {"type": "string"}, "limit": {"type": "integer", "description": "max results, default 8"}}, ["query"]), _wiki_search),
    Tool("wiki_read", "Read a file in the AI-Wiki folder, e.g. 'index.md', 'log.md', 'SCHEMA.md', 'wiki/concepts/Zero Trust.md', 'raw/article.md'. A folder path lists its files.",
         _obj({"path": {"type": "string"}}, ["path"]), wiki.read),
    Tool("wiki_list", "List files under a folder of the AI-Wiki (e.g. 'wiki', 'wiki/concepts', 'raw', 'daily', 'reports').",
         _obj({"folder": {"type": "string"}}, []), _wiki_list),
    Tool("wiki_write", "Create or overwrite (or append to) a markdown file. Allowed: wiki/**, daily/**, reports/**, index.md, log.md. raw/ is read-only. Use Obsidian [[wikilinks]].",
         _obj({"path": {"type": "string"}, "content": {"type": "string"}, "mode": {"type": "string", "enum": ["overwrite", "append"]}}, ["path", "content"]), _wiki_write),
    Tool("wiki_log", "Append one line to log.md. verb is one of ingest, query, lint, checkin, report.",
         _obj({"verb": {"type": "string"}, "text": {"type": "string"}}, ["verb", "text"]), _wiki_log),
    Tool("habit_log", "Log a habit entry. kind: gym | reading | study | finance | other. value: minutes for reading/study/finance, 1 per gym session. note: details (e.g. 'Push day: bench 3x8 185lb', book title, Security+ domain).",
         _obj({"kind": {"type": "string", "enum": habits.KINDS}, "value": {"type": "number"}, "unit": {"type": "string"},
               "note": {"type": "string"}, "day": {"type": "string", "description": "YYYY-MM-DD, default today"}}, ["kind", "value"]), _habit_log),
    Tool("habit_summary", "Get habit totals, goal progress and streaks for the last N days.",
         _obj({"days": {"type": "integer"}}, ["days"]), _habit_summary),
    Tool("get_goals", "Get the user's current goals (reading minutes/day, gym sessions/week, study minutes/day, current cert).",
         _obj({}, []), _goals),
]}

WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}
WEB_FETCH = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5}

GROUPS: dict[str, dict] = {
    "wiki_read": {"label": "Wiki: read & search", "tools": ["wiki_search", "wiki_read", "wiki_list"]},
    "wiki_write": {"label": "Wiki: write & log", "tools": ["wiki_write", "wiki_log"]},
    "habits": {"label": "Habits & goals", "tools": ["habit_log", "habit_summary", "get_goals"]},
    "web": {"label": "Web search & fetch", "server": [WEB_SEARCH, WEB_FETCH]},
}


def build(groups: list[str], extra: list[Tool] | None = None) -> tuple[list[dict], Callable[[str, dict], str]]:
    defs: list[dict] = []
    local: dict[str, Tool] = {}
    for g in groups or []:
        spec = GROUPS.get(g)
        if not spec:
            continue
        for name in spec.get("tools", []):
            local[name] = TOOLS[name]
        defs.extend(spec.get("server", []))
    for t in extra or []:
        local[t.name] = t
    defs = [t.definition() for t in local.values()] + defs

    def handle(name: str, args: dict) -> str:
        tool = local.get(name)
        if not tool:
            raise ValueError(f"Unknown tool {name}")
        out = tool.fn(**args)
        return out if isinstance(out, str) else json.dumps(out)

    return defs, handle
