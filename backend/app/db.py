"""Tiny SQLite layer. One shared connection guarded by a lock (local single-user app)."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any

from .config import DB_PATH

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
    graph TEXT NOT NULL, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, workflow_id TEXT, workflow_name TEXT, trigger TEXT, status TEXT,
    input TEXT, output TEXT, error TEXT, steps TEXT, cost_usd REAL DEFAULT 0,
    started_at TEXT, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, kind TEXT NOT NULL,
    value REAL DEFAULT 0, unit TEXT DEFAULT '', note TEXT DEFAULT '', created_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY, title TEXT, messages TEXT, display TEXT, cost_usd REAL DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ingested (path TEXT PRIMARY KEY, mtime REAL, ingested_at TEXT);
CREATE TABLE IF NOT EXISTS spend (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, source TEXT, model TEXT, cost_usd REAL);
"""

DEFAULT_SETTINGS = {
    "reading_goal_minutes": "30",
    "gym_goal_per_week": "4",
    "study_goal_minutes": "45",
    "current_cert": "CompTIA Security+",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
            for k, v in DEFAULT_SETTINGS.items():
                _conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
            _conn.commit()
        return _conn


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list = ()) -> int:
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur.lastrowid or 0


# ---- settings -------------------------------------------------------------
def get_settings() -> dict[str, str]:
    return {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}


def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---- spend ----------------------------------------------------------------
def record_spend(source: str, model: str, cost: float) -> None:
    if cost > 0:
        execute("INSERT INTO spend(at, source, model, cost_usd) VALUES (?, ?, ?, ?)", (now(), source, model, cost))


def month_spend() -> float:
    prefix = datetime.now().strftime("%Y-%m")
    row = one("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM spend WHERE at LIKE ?", (prefix + "%",))
    return float(row["total"]) if row else 0.0


# ---- workflows ------------------------------------------------------------
def workflow_row(row: dict) -> dict:
    row = dict(row)
    row["graph"] = json.loads(row["graph"])
    row["enabled"] = bool(row["enabled"])
    return row


def list_workflows() -> list[dict]:
    return [workflow_row(r) for r in query("SELECT * FROM workflows ORDER BY name")]


def get_workflow(wf_id: str) -> dict | None:
    row = one("SELECT * FROM workflows WHERE id = ?", (wf_id,))
    return workflow_row(row) if row else None


def save_workflow(wf: dict) -> dict:
    wf_id = wf.get("id") or new_id()
    existing = one("SELECT id FROM workflows WHERE id = ?", (wf_id,))
    graph = json.dumps(wf.get("graph") or {"nodes": [], "edges": []})
    if existing:
        execute(
            "UPDATE workflows SET name=?, description=?, graph=?, enabled=?, updated_at=? WHERE id=?",
            (wf["name"], wf.get("description", ""), graph, int(wf.get("enabled", True)), now(), wf_id),
        )
    else:
        execute(
            "INSERT INTO workflows(id, name, description, graph, enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (wf_id, wf["name"], wf.get("description", ""), graph, int(wf.get("enabled", True)), now(), now()),
        )
    return get_workflow(wf_id)  # type: ignore[return-value]


def delete_workflow(wf_id: str) -> None:
    execute("DELETE FROM workflows WHERE id = ?", (wf_id,))
