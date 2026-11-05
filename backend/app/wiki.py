"""Obsidian "LLM Wiki" (Karpathy pattern): raw/ sources -> LLM-maintained wiki/ + index.md + log.md.

Everything lives in <vault>/AI-Wiki so the rest of your vault is never touched.
raw/ is read-only for the AI; wiki/, daily/, reports/, index.md and log.md are AI-writable."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import db
from .config import WIKI_ROOT

SUBDIRS = ["raw", "wiki", "wiki/sources", "wiki/concepts", "wiki/topics", "wiki/answers", "daily", "reports"]
WRITABLE_PREFIXES = ("wiki/", "daily/", "reports/")
WRITABLE_FILES = ("index.md", "log.md")
TEXT_EXTS = {".md", ".txt", ".markdown", ".csv", ".json", ".html", ".htm"}
INGESTABLE_EXTS = TEXT_EXTS | {".pdf"}

SCHEMA_TEMPLATE = """# AI-Wiki Schema

This file tells the AI how to maintain this wiki. Edit it any time - the AI re-reads it on every ingest.

## Purpose
A personal knowledge base that compounds over time. Organize knowledge around my goals:
- **Fitness**: take the gym seriously (progressive overload, consistency).
- **Reading**: read every day; turn books into notes.
- **Cybersecurity career**: currently studying for **CompTIA Security+**, then more certs.
- **Financial literacy**: budgeting, credit, investing basics, taxes (educational, not advice).
- **Software dev**: code, tools, and projects I'm learning.

## Layers
- `raw/` - original sources I drop in (articles, PDFs, clips). **Never edit or delete.**
- `wiki/` - pages the AI writes and maintains:
  - `wiki/sources/<slug>.md` - one summary page per ingested source.
  - `wiki/concepts/<Concept Name>.md` - one page per idea/term (e.g. `Zero Trust.md`, `Compound Interest.md`).
  - `wiki/topics/<Topic>.md` - hub pages that tie concepts together (e.g. `Security+ Domain 2 - Threats.md`).
  - `wiki/answers/<slug>.md` - good answers to questions, filed back so explorations compound.
- `daily/YYYY-MM-DD.md` - daily habit check-in notes.
- `reports/` - weekly growth reports and lint reports.
- `index.md` - catalog of every wiki page with a one-line summary, grouped by category.
- `log.md` - append-only activity log.

## Page conventions
- Start every wiki page with YAML frontmatter:
  ```
  ---
  type: source | concept | topic | answer
  tags: [security-plus, finance, fitness, reading, dev]
  sources: [[sources/<slug>]]
  updated: YYYY-MM-DD
  ---
  ```
- Link generously with Obsidian wikilinks: `[[Zero Trust]]`, `[[sources/nist-800-207]]`.
- Prefer updating an existing page over creating a near-duplicate. Search first.
- Concept pages: short definition, why it matters to my goals, key details, related links, sources.
- When sources disagree, note the contradiction explicitly under a `## Conflicts` heading.
- Security+ content: tag the exam domain (e.g. `Domain 1: General Security Concepts`).

## Log format
One line per action, newest at the bottom:
`- [YYYY-MM-DD HH:MM] ingest | <source title> | pages: a, b, c`
Other verbs: `query`, `lint`, `checkin`, `report`.
"""


def ensure_structure() -> None:
    for d in SUBDIRS:
        (WIKI_ROOT / d).mkdir(parents=True, exist_ok=True)
    defaults = {
        "SCHEMA.md": SCHEMA_TEMPLATE,
        "index.md": "# Wiki Index\n\nCatalog of all wiki pages, grouped by category. Maintained by the AI.\n\n## Sources\n\n## Concepts\n\n## Topics\n\n## Answers\n",
        "log.md": "# Wiki Log\n\nAppend-only activity log.\n\n",
        "raw/README.md": "Drop sources here (articles as .md, PDFs, text). The app auto-ingests new files into the wiki.\n",
    }
    for rel, content in defaults.items():
        p = WIKI_ROOT / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")


def schema() -> str:
    p = WIKI_ROOT / "SCHEMA.md"
    return p.read_text(encoding="utf-8") if p.exists() else SCHEMA_TEMPLATE


def safe_path(rel: str, *, write: bool = False) -> Path:
    rel = rel.replace("\\", "/").lstrip("/")
    if rel.startswith(WIKI_ROOT.name + "/"):
        rel = rel[len(WIKI_ROOT.name) + 1:]
    p = (WIKI_ROOT / rel).resolve()
    root = WIKI_ROOT.resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"Path escapes the wiki folder: {rel}")
    if write:
        norm = p.relative_to(root).as_posix()
        if not (norm.startswith(WRITABLE_PREFIXES) or norm in WRITABLE_FILES):
            raise ValueError(f"Not allowed to write '{norm}'. Writable: wiki/, daily/, reports/, index.md, log.md")
        if p.suffix.lower() != ".md":
            raise ValueError("Only .md files can be written")
    return p


def rel(p: Path) -> str:
    return p.resolve().relative_to(WIKI_ROOT.resolve()).as_posix()


def read(path: str) -> str:
    p = safe_path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if p.is_dir():
        return "\n".join(sorted(rel(c) for c in p.iterdir()))
    return p.read_text(encoding="utf-8", errors="replace")


def write(path: str, content: str, mode: str = "overwrite") -> str:
    p = safe_path(path, write=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and p.exists():
        with p.open("a", encoding="utf-8") as f:
            f.write(("" if content.startswith("\n") else "\n") + content)
    else:
        p.write_text(content, encoding="utf-8")
    return rel(p)


def append_log(verb: str, text: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    write("log.md", f"- [{stamp}] {verb} | {text}", mode="append")


def list_files(folder: str = "wiki") -> list[str]:
    base = safe_path(folder)
    if not base.exists():
        return []
    return sorted(rel(p) for p in base.rglob("*") if p.is_file() and not p.name.startswith("."))


def search(query: str, limit: int = 8) -> list[dict]:
    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2] or [query.lower()]
    hits = []
    for folder in ("wiki", "daily", "reports"):
        for path in list_files(folder):
            if not path.endswith(".md"):
                continue
            text = (WIKI_ROOT / path).read_text(encoding="utf-8", errors="replace")
            low, name = text.lower(), path.lower()
            score = sum(low.count(t) + 5 * name.count(t) for t in terms)
            if score:
                idx = min((low.find(t) for t in terms if t in low), default=0)
                snippet = text[max(0, idx - 120): idx + 240].replace("\n", " ")
                hits.append({"path": path, "score": score, "snippet": snippet})
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


# ---- ingest bookkeeping ---------------------------------------------------
def pending_raw() -> list[str]:
    done = {r["path"]: r["mtime"] for r in db.query("SELECT path, mtime FROM ingested")}
    out = []
    for path in list_files("raw"):
        p = WIKI_ROOT / path
        if p.suffix.lower() not in INGESTABLE_EXTS or p.name.lower() == "readme.md":
            continue
        if done.get(path) != p.stat().st_mtime:
            out.append(path)
    return out


def mark_ingested(path: str) -> None:
    p = safe_path(path)
    db.execute(
        "INSERT INTO ingested(path, mtime, ingested_at) VALUES (?,?,?) ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, ingested_at=excluded.ingested_at",
        (rel(p), p.stat().st_mtime, db.now()),
    )


def source_content_blocks(path: str) -> list[dict]:
    """Content blocks for a raw source: PDFs go to Claude natively as documents."""
    import base64

    p = safe_path(path)
    if p.suffix.lower() == ".pdf":
        data = base64.standard_b64encode(p.read_bytes()).decode("ascii")
        return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}, "title": p.name}]
    return [{"type": "text", "text": f"<source path=\"{rel(p)}\">\n{p.read_text(encoding='utf-8', errors='replace')}\n</source>"}]
