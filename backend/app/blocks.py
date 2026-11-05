"""Block registry: every block type you can drop on the canvas.

Each block declares its inspector fields (rendered automatically by the frontend) and an
`run(ctx, cfg)` function returning a BlockResult. Templates use {{input}}, {{prev}}, {{today}},
{{now}}, {{week}} and {{<node_id>}} (output of any earlier node)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from . import habits, llm, notify, tools, wiki
from .config import DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, MODELS

if TYPE_CHECKING:
    from .engine import RunContext


@dataclass
class BlockResult:
    output: str
    branch: str | None = None  # condition blocks: "true" / "false"


@dataclass
class BlockType:
    type: str
    name: str
    category: str
    color: str
    icon: str
    description: str
    fields: list[dict]
    run: Callable[["RunContext", dict], BlockResult]
    is_trigger: bool = False
    outputs: list[str] = field(default_factory=lambda: ["out"])

    def meta(self) -> dict:
        return {k: getattr(self, k) for k in ("type", "name", "category", "color", "icon", "description", "fields", "is_trigger", "outputs")}


REGISTRY: dict[str, BlockType] = {}


def register(bt: BlockType) -> None:
    REGISTRY[bt.type] = bt


# ---- shared field helpers ---------------------------------------------------
MODEL_OPTIONS = [{"value": k, "label": v["label"]} for k, v in MODELS.items()]
EFFORT_OPTIONS = [{"value": e, "label": e} for e in EFFORTS]
TOOL_OPTIONS = [{"value": k, "label": v["label"]} for k, v in tools.GROUPS.items()]


def f_model() -> dict:
    return {"key": "model", "label": "Model", "type": "select", "options": MODEL_OPTIONS, "default": DEFAULT_MODEL}


def f_effort(default: str = DEFAULT_EFFORT) -> dict:
    return {"key": "effort", "label": "Effort", "type": "select", "options": EFFORT_OPTIONS, "default": default,
            "help": "Lower = cheaper and faster. Raise for hard reasoning."}


# ---- triggers ---------------------------------------------------------------
def _trigger_passthrough(ctx: "RunContext", cfg: dict) -> BlockResult:
    return BlockResult(ctx.input or cfg.get("default_input", ""))


register(BlockType("trigger.manual", "Manual run", "Triggers", "#e30613", "MN",
                   "Starts when you click Run. Output = the text you type in.",
                   [{"key": "default_input", "label": "Default input", "type": "textarea", "default": ""}],
                   _trigger_passthrough, is_trigger=True))

register(BlockType("trigger.chat", "Chat", "Triggers", "#e30613", "CH",
                   "Starts when the chat assistant runs this workflow. Output = the chat request.",
                   [], _trigger_passthrough, is_trigger=True))

register(BlockType("trigger.schedule", "Schedule", "Triggers", "#e30613", "SC",
                   "Runs on a cron schedule while the app is running (your PC must be on).",
                   [{"key": "cron", "label": "Cron (min hour day month weekday)", "type": "text", "default": "0 7 * * *",
                     "help": "Examples: '0 7 * * *' = 7:00 daily, '30 20 * * *' = 8:30pm daily, '0 18 * * sun' = Sundays 6pm."}],
                   lambda ctx, cfg: BlockResult(ctx.input or f"Scheduled run at {ctx.vars()['now']}"), is_trigger=True))

register(BlockType("trigger.folder", "Watch raw/ folder", "Triggers", "#e30613", "FD",
                   "Runs when a new file lands in AI-Wiki/raw (e.g. from Obsidian Web Clipper). Output = the file path.",
                   [], lambda ctx, cfg: BlockResult(ctx.payload.get("path", ctx.input or "")), is_trigger=True))


# ---- AI -----------------------------------------------------------------------
def _agent(ctx: "RunContext", cfg: dict) -> BlockResult:
    defs, handler = tools.build(cfg.get("tools") or [])
    system = ctx.render(cfg.get("system") or "You are a helpful assistant.")
    system += f"\n\nToday is {ctx.vars()['today']} ({ctx.vars()['weekday']})."
    res = llm.run_agent(
        system=system,
        messages=[{"role": "user", "content": ctx.render(cfg.get("prompt") or "{{prev}}")}],
        tool_defs=defs or None, tool_handler=handler,
        model=cfg.get("model"), effort=cfg.get("effort"),
        max_turns=int(cfg.get("max_turns") or 15), source=f"workflow:{ctx.workflow_name}", on_event=ctx.log,
    )
    ctx.add_cost(res.cost)
    return BlockResult(res.text)


register(BlockType("ai.agent", "AI Agent", "AI", "#111111", "AI",
                   "A Claude agent with a prompt and optional tools (wiki, habits, web).",
                   [f_model(), f_effort(),
                    {"key": "system", "label": "System prompt (role)", "type": "textarea", "default": "You are a helpful assistant."},
                    {"key": "prompt", "label": "Prompt", "type": "textarea", "default": "{{prev}}"},
                    {"key": "tools", "label": "Tools", "type": "multiselect", "options": TOOL_OPTIONS, "default": []},
                    {"key": "max_turns", "label": "Max tool turns", "type": "number", "default": 15}],
                   _agent))


# ---- wiki ---------------------------------------------------------------------
INGEST_SYSTEM = """You are the maintainer of the user's personal Obsidian wiki ("LLM Wiki" pattern).
You compile sources into a persistent, interlinked wiki so knowledge compounds over time.

Follow the wiki's schema exactly:
<schema>
{schema}
</schema>

Ingest procedure for the source you are given:
1. Read index.md and search the wiki for related existing pages.
2. Write wiki/sources/<slug>.md: summary, key takeaways, notable quotes/data, and how it relates to the user's goals.
3. Create or update concept/topic pages for the important ideas (typically 3-12 pages). Update existing pages instead of duplicating; note contradictions.
4. Update index.md so every page you created is listed with a one-line summary under the right category (rewrite the whole file, keep existing entries).
5. Append one line to log.md with wiki_log (verb "ingest").
Finish with a short plain-text report: source title, pages created, pages updated, and 2-3 follow-up questions worth exploring."""


def _ingest(ctx: "RunContext", cfg: dict) -> BlockResult:
    target = (ctx.payload.get("path") or "").strip()
    if not target and cfg.get("path_template"):
        target = ctx.render(cfg["path_template"]).strip()
    paths = [wiki.rel(wiki.safe_path(target))] if target else wiki.pending_raw()
    if not paths:
        return BlockResult("Nothing new to ingest in raw/.")
    defs, handler = tools.build(["wiki_read", "wiki_write"])
    system = INGEST_SYSTEM.format(schema=wiki.schema())
    reports = []
    for p in paths[: int(cfg.get("max_files") or 5)]:
        ctx.log(f"ingesting {p}")
        content = wiki.source_content_blocks(p) + [{"type": "text", "text": f"Ingest this source (raw path: {p}) into the wiki."}]
        res = llm.run_agent(system=system, messages=[{"role": "user", "content": content}], tool_defs=defs,
                            tool_handler=handler, model=cfg.get("model"), effort=cfg.get("effort"),
                            max_turns=40, source=f"workflow:{ctx.workflow_name}", on_event=ctx.log)
        ctx.add_cost(res.cost)
        wiki.mark_ingested(p)
        reports.append(f"### {p}\n{res.text}")
    left = len(paths) - len(reports)
    if left > 0:
        reports.append(f"({left} more file(s) waiting - run again to continue.)")
    return BlockResult("\n\n".join(reports))


register(BlockType("wiki.ingest", "Wiki: Ingest", "Obsidian Wiki", "#0047ab", "IN",
                   "Turns raw/ sources into linked wiki pages, updates index.md and log.md.",
                   [f_model(), f_effort("medium"),
                    {"key": "max_files", "label": "Max files per run", "type": "number", "default": 5},
                    {"key": "path_template", "label": "Specific raw file (optional)", "type": "text", "default": "",
                     "help": "Leave empty to ingest every new/changed file in raw/."}],
                   _ingest))


QUERY_SYSTEM = """You answer questions using the user's personal Obsidian wiki.
Start by reading index.md, then search and read the relevant pages. Base your answer on the wiki and cite pages
with Obsidian wikilinks like [[concepts/Zero Trust]]. If the wiki doesn't cover something, say so clearly
and suggest a source to ingest.{file_back}

Wiki schema for reference:
<schema>
{schema}
</schema>"""

FILE_BACK = """
If your answer is a substantial synthesis worth keeping, also save it with wiki_write to
wiki/answers/<short-slug>.md (frontmatter type: answer), add it to index.md under Answers, and log it (verb "query")."""


def _query(ctx: "RunContext", cfg: dict) -> BlockResult:
    file_back = bool(cfg.get("file_back", True))
    defs, handler = tools.build(["wiki_read", "wiki_write"] if file_back else ["wiki_read"])
    res = llm.run_agent(system=QUERY_SYSTEM.format(file_back=FILE_BACK if file_back else "", schema=wiki.schema()),
                        messages=[{"role": "user", "content": ctx.render(cfg.get("question") or "{{input}}")}],
                        tool_defs=defs, tool_handler=handler, model=cfg.get("model"), effort=cfg.get("effort"),
                        max_turns=25, source=f"workflow:{ctx.workflow_name}", on_event=ctx.log)
    ctx.add_cost(res.cost)
    return BlockResult(res.text)


register(BlockType("wiki.query", "Wiki: Ask", "Obsidian Wiki", "#0047ab", "AS",
                   "Answers a question from your wiki with [[citations]]; optionally files good answers back.",
                   [f_model(), f_effort("low"),
                    {"key": "question", "label": "Question", "type": "textarea", "default": "{{input}}"},
                    {"key": "file_back", "label": "Save good answers to wiki/answers", "type": "bool", "default": True}],
                   _query))


LINT_SYSTEM = """You health-check the user's Obsidian wiki. Read index.md, list and skim pages, and look for:
contradictions between pages, stale claims, orphan pages (not in index or never linked), important concepts
mentioned but lacking their own page, missing cross-links, and data gaps. Fix small issues directly (add links,
index entries). Write a report to reports/lint-{today}.md listing what you fixed and what needs the user's input,
then log it (verb "lint"). Finish with a brief summary.

Schema:
<schema>
{schema}
</schema>"""


def _lint(ctx: "RunContext", cfg: dict) -> BlockResult:
    defs, handler = tools.build(["wiki_read", "wiki_write"])
    res = llm.run_agent(system=LINT_SYSTEM.format(today=ctx.vars()["today"], schema=wiki.schema()),
                        messages=[{"role": "user", "content": "Run a lint pass on the wiki now."}],
                        tool_defs=defs, tool_handler=handler, model=cfg.get("model"), effort=cfg.get("effort"),
                        max_turns=40, source=f"workflow:{ctx.workflow_name}", on_event=ctx.log)
    ctx.add_cost(res.cost)
    return BlockResult(res.text)


register(BlockType("wiki.lint", "Wiki: Lint", "Obsidian Wiki", "#0047ab", "LT",
                   "Health check: contradictions, orphans, missing pages and links. Writes a report.",
                   [f_model(), f_effort("medium")], _lint))


def _note(ctx: "RunContext", cfg: dict) -> BlockResult:
    path = ctx.render(cfg.get("path") or "reports/note-{{today}}.md").strip()
    written = wiki.write(path, ctx.render(cfg.get("content") or "{{prev}}"), cfg.get("mode") or "overwrite")
    if cfg.get("log_verb"):
        wiki.append_log(cfg["log_verb"], f"wrote [[{written[:-3]}]]")
    ctx.log(f"wrote {written}")
    return BlockResult(ctx.vars()["prev"] if cfg.get("pass_through", True) else written)


register(BlockType("wiki.note", "Wiki: Write note", "Obsidian Wiki", "#0047ab", "NT",
                   "Writes or appends a markdown note inside AI-Wiki (wiki/, daily/, reports/).",
                   [{"key": "path", "label": "Path (inside AI-Wiki)", "type": "text", "default": "reports/note-{{today}}.md"},
                    {"key": "content", "label": "Content", "type": "textarea", "default": "{{prev}}"},
                    {"key": "mode", "label": "Mode", "type": "select", "default": "overwrite",
                     "options": [{"value": "overwrite", "label": "overwrite"}, {"value": "append", "label": "append"}]},
                    {"key": "log_verb", "label": "Log verb for log.md (optional)", "type": "text", "default": ""}],
                   _note))


# ---- habits -------------------------------------------------------------------
register(BlockType("habits.summary", "Habits: Summary", "Habits", "#d9a400", "SU",
                   "Text summary of habit totals, goal progress and streaks.",
                   [{"key": "days", "label": "Days to include", "type": "number", "default": 7}],
                   lambda ctx, cfg: BlockResult(habits.summary_text(int(cfg.get("days") or 7)))))


def _habit_log(ctx: "RunContext", cfg: dict) -> BlockResult:
    value = float(ctx.render(str(cfg.get("value", "1"))).strip() or 0)
    e = habits.log(cfg.get("kind") or "other", value, cfg.get("unit") or "", ctx.render(cfg.get("note") or ""))
    return BlockResult(f"Logged {e['kind']}: {e['value']} {e['unit']} {e['note']}".strip())


register(BlockType("habits.log", "Habits: Log", "Habits", "#d9a400", "LG",
                   "Logs a fixed habit entry (for AI-parsed check-ins, use an AI Agent with the Habits tool).",
                   [{"key": "kind", "label": "Kind", "type": "select", "default": "reading",
                     "options": [{"value": k, "label": k} for k in habits.KINDS]},
                    {"key": "value", "label": "Value (minutes / sessions)", "type": "text", "default": "1"},
                    {"key": "unit", "label": "Unit", "type": "text", "default": ""},
                    {"key": "note", "label": "Note", "type": "text", "default": ""}],
                   _habit_log))


# ---- logic & utilities ----------------------------------------------------------
def _template(ctx: "RunContext", cfg: dict) -> BlockResult:
    return BlockResult(ctx.render(cfg.get("template") or "{{prev}}"))


register(BlockType("util.template", "Text template", "Logic", "#8a8a85", "TX",
                   "Builds text from variables, e.g. combine outputs of several blocks.",
                   [{"key": "template", "label": "Template", "type": "textarea", "default": "{{prev}}"}], _template))


def _condition(ctx: "RunContext", cfg: dict) -> BlockResult:
    text = ctx.render(cfg.get("input") or "{{prev}}")
    mode, val = cfg.get("mode") or "contains", ctx.render(cfg.get("value") or "")
    low, vlow = text.strip().lower(), val.strip().lower()
    if mode == "contains":
        ok = vlow in low
    elif mode == "not_contains":
        ok = vlow not in low
    elif mode == "empty":
        ok = not low
    elif mode == "not_empty":
        ok = bool(low)
    elif mode in ("number_lt", "number_gt"):
        try:
            n, v = float(low), float(vlow)
        except ValueError:
            ok = False
        else:
            ok = n < v if mode == "number_lt" else n > v
    else:
        raise ValueError(f"Unknown condition mode {mode}")
    ctx.log(f"condition {mode} '{val}' → {ok}")
    return BlockResult(ctx.vars()["prev"], branch="true" if ok else "false")


register(BlockType("logic.condition", "Condition", "Logic", "#8a8a85", "IF",
                   "Routes to the 'true' or 'false' output. Downstream blocks on the other branch are skipped.",
                   [{"key": "input", "label": "Text to test", "type": "textarea", "default": "{{prev}}"},
                    {"key": "mode", "label": "Check", "type": "select", "default": "contains",
                     "options": [{"value": m, "label": m} for m in ["contains", "not_contains", "empty", "not_empty", "number_lt", "number_gt"]]},
                    {"key": "value", "label": "Value", "type": "text", "default": ""}],
                   _condition, outputs=["true", "false"]))


def _notify(ctx: "RunContext", cfg: dict) -> BlockResult:
    title = ctx.render(cfg.get("title") or "SIMS AI Office")
    msg = ctx.render(cfg.get("message") or "{{prev}}")
    notify.toast(title, msg)
    return BlockResult(msg)


register(BlockType("util.notify", "Windows notification", "Output", "#111111", "NO",
                   "Shows a Windows desktop notification.",
                   [{"key": "title", "label": "Title", "type": "text", "default": "SIMS AI Office"},
                    {"key": "message", "label": "Message", "type": "textarea", "default": "{{prev}}"}],
                   _notify))


def catalog() -> list[dict]:
    return [b.meta() for b in REGISTRY.values()]
