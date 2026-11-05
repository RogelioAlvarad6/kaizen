"""Background triggers: cron schedules (APScheduler) and the raw/ folder watcher (watchdog)."""
from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from . import engine, wiki
from .config import WIKI_ROOT

log = logging.getLogger("sims.triggers")
scheduler = BackgroundScheduler()
_observer: Observer | None = None


# ---- schedules ---------------------------------------------------------------
def _fire(wf_id: str, node_id: str) -> None:
    try:
        engine.start_run(wf_id, "schedule", "", {"trigger_node_ids": [node_id]})
    except Exception as e:
        log.error("scheduled run failed to start: %s", e)


def reload_schedules() -> list[dict]:
    scheduler.remove_all_jobs()
    jobs = []
    for wf, nodes in engine.workflows_with_trigger("schedule"):
        for n in nodes:
            cron = ((n["data"].get("config") or {}).get("cron") or "").strip()
            if not cron:
                continue
            try:
                job = scheduler.add_job(_fire, CronTrigger.from_crontab(cron), args=[wf["id"], n["id"]],
                                        id=f"{wf['id']}:{n['id']}", replace_existing=True, misfire_grace_time=3600)
                jobs.append({"workflow": wf["name"], "cron": cron})
                log.info("scheduled %s (%s)", wf["name"], cron)
            except ValueError as e:
                log.error("bad cron '%s' in %s: %s", cron, wf["name"], e)
    return jobs


def scheduled_jobs() -> list[dict]:
    out = []
    for job in scheduler.get_jobs():
        wf_id = job.id.split(":")[0]
        wf = engine.db.get_workflow(wf_id)
        out.append({"workflow_id": wf_id, "workflow": wf["name"] if wf else wf_id,
                    "next_run": job.next_run_time.isoformat(timespec="minutes") if job.next_run_time else None})
    return sorted(out, key=lambda j: j["next_run"] or "")


# ---- raw/ folder watcher -------------------------------------------------------
class _RawHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self._timers: dict[str, threading.Timer] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        self._queue(event.src_path, event.is_directory)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._queue(getattr(event, "dest_path", event.src_path), event.is_directory)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._queue(event.src_path, event.is_directory)

    def _queue(self, path: str, is_dir: bool) -> None:
        if is_dir:
            return
        # debounce: wait until the file has stopped changing for 5s
        if path in self._timers:
            self._timers[path].cancel()
        t = threading.Timer(5.0, self._fire, args=[path])
        self._timers[path] = t
        t.start()

    def _fire(self, path: str) -> None:
        self._timers.pop(path, None)
        try:
            rel = wiki.rel(wiki.safe_path(path))
        except Exception:
            return
        if rel not in wiki.pending_raw():
            return  # not ingestable, README, or unchanged since last ingest
        for wf, _nodes in engine.workflows_with_trigger("folder"):
            log.info("raw file %s → %s", rel, wf["name"])
            engine.start_run(wf["id"], "folder", rel, {"path": rel})


def start() -> None:
    global _observer
    if not scheduler.running:
        scheduler.start()
    reload_schedules()
    raw = WIKI_ROOT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    _observer = Observer()
    _observer.schedule(_RawHandler(), str(raw), recursive=False)
    _observer.daemon = True
    _observer.start()
    log.info("watching %s", raw)


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if _observer:
        _observer.stop()
