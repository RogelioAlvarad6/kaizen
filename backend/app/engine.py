"""Workflow engine: executes a canvas graph in topological order on a background thread.

Graph shape (React Flow): nodes = [{id, position, data: {blockType, label, config}}],
edges = [{id, source, target, sourceHandle?}].
Activation: the trigger nodes matching the run's trigger type start the run (if none match, all
triggers do). A non-trigger node runs if any incoming edge comes from a node that ran, and - for
condition nodes - the edge's sourceHandle matches the branch taken."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import traceback
from datetime import datetime
from typing import Any

from . import db
from .blocks import REGISTRY, BlockResult

log = logging.getLogger("sims.engine")
VAR_RE = re.compile(r"\{\{\s*([\w\-.:]+)\s*\}\}")


class RunContext:
    def __init__(self, run_id: str, workflow: dict, trigger: str, input_text: str, payload: dict):
        self.run_id = run_id
        self.workflow_name = workflow["name"]
        self.trigger = trigger
        self.input = input_text or ""
        self.payload = payload or {}
        self.outputs: dict[str, str] = {}
        self.current_prev = ""
        self.cost = 0.0
        self.steps: list[dict] = []
        self._step: dict | None = None

    def vars(self) -> dict[str, str]:
        n = datetime.now()
        iso = n.isocalendar()
        return {"input": self.input, "prev": self.current_prev, "today": n.date().isoformat(),
                "now": n.strftime("%Y-%m-%d %H:%M"), "week": f"{iso[0]}-W{iso[1]:02d}", "weekday": n.strftime("%A")}

    def render(self, template: str) -> str:
        values = {**self.vars(), **self.outputs}
        return VAR_RE.sub(lambda m: values.get(m.group(1), m.group(0)), template or "")

    def log(self, msg: str) -> None:
        if self._step is not None:
            self._step.setdefault("events", []).append(f"{datetime.now():%H:%M:%S} {msg}")
            self.save()

    def add_cost(self, c: float) -> None:
        self.cost += c
        if self._step is not None:
            self._step["cost"] = self._step.get("cost", 0) + c

    def save(self, **fields: Any) -> None:
        sets = {"steps": json.dumps(self.steps, ensure_ascii=False), "cost_usd": round(self.cost, 6), **fields}
        cols = ", ".join(f"{k} = ?" for k in sets)
        db.execute(f"UPDATE runs SET {cols} WHERE id = ?", [*sets.values(), self.run_id])


def topo_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    ids = [n["id"] for n in nodes]
    indeg = {i: 0 for i in ids}
    for e in edges:
        if e["target"] in indeg and e["source"] in indeg:
            indeg[e["target"]] += 1
    ready = [i for i in ids if indeg[i] == 0]
    order = []
    while ready:
        cur = ready.pop(0)
        order.append(cur)
        for e in edges:
            if e["source"] == cur and e["target"] in indeg:
                indeg[e["target"]] -= 1
                if indeg[e["target"]] == 0:
                    ready.append(e["target"])
    if len(order) != len(ids):
        raise ValueError("Workflow has a cycle - remove the loop between blocks.")
    return order


def execute(run_id: str, wf: dict, trigger: str, input_text: str, payload: dict) -> None:
    ctx = RunContext(run_id, wf, trigger, input_text, payload)
    graph = wf["graph"]
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = [e for e in graph.get("edges", []) if e.get("source") in nodes and e.get("target") in nodes]

    def btype(nid: str):
        return REGISTRY.get(nodes[nid]["data"].get("blockType", ""))

    try:
        order = topo_order(list(nodes.values()), edges)
        triggers = [i for i in order if (bt := btype(i)) and bt.is_trigger]
        wanted = payload.get("trigger_node_ids") or [i for i in triggers if btype(i).type == f"trigger.{trigger}"]
        active_triggers = set(wanted or triggers)
        if not triggers:  # no trigger blocks: start from the roots
            active_triggers = {i for i in order if not any(e["target"] == i for e in edges)}

        ran: dict[str, BlockResult] = {}
        final_output = ""
        for nid in order:
            node = nodes[nid]
            bt = btype(nid)
            label = node["data"].get("label") or (bt.name if bt else nid)
            incoming = [e for e in edges if e["target"] == nid]
            if bt and bt.is_trigger or not incoming:
                active = nid in active_triggers
            else:
                active = False
                for e in incoming:
                    src = ran.get(e["source"])
                    if src is None:
                        continue
                    handle = e.get("sourceHandle") or "out"
                    if src.branch is None or handle == src.branch:
                        active = True
            if not active:
                continue
            if bt is None:
                raise ValueError(f"Unknown block type '{node['data'].get('blockType')}' on node {nid}")

            ctx.current_prev = "\n\n".join(ran[e["source"]].output for e in incoming if e["source"] in ran and ran[e["source"]].output)
            step = {"node_id": nid, "label": label, "type": bt.type, "status": "running", "started_at": db.now(), "events": [], "cost": 0}
            ctx.steps.append(step)
            ctx._step = step
            ctx.save()
            t0 = time.time()
            try:
                res = bt.run(ctx, node["data"].get("config") or {})
            except Exception as e:
                step.update(status="error", error=str(e), seconds=round(time.time() - t0, 1))
                raise
            ran[nid] = res
            ctx.outputs[nid] = res.output
            final_output = res.output or final_output
            step.update(status="done", output=res.output, branch=res.branch, seconds=round(time.time() - t0, 1))
            ctx._step = None
            ctx.save()

        ctx.save(status="success", output=final_output, finished_at=db.now())
    except Exception as e:
        log.error("run %s failed: %s", run_id, traceback.format_exc())
        ctx._step = None
        ctx.save(status="error", error=str(e), finished_at=db.now())


def start_run(wf_id: str, trigger: str = "manual", input_text: str = "", payload: dict | None = None) -> str:
    wf = db.get_workflow(wf_id)
    if not wf:
        raise KeyError(f"workflow {wf_id} not found")
    run_id = db.new_id()
    db.execute(
        "INSERT INTO runs(id, workflow_id, workflow_name, trigger, status, input, output, error, steps, started_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (run_id, wf_id, wf["name"], trigger, "running", input_text or "", "", "", "[]", db.now()),
    )
    threading.Thread(target=execute, args=(run_id, wf, trigger, input_text, payload or {}), daemon=True).start()
    return run_id


def get_run(run_id: str) -> dict | None:
    row = db.one("SELECT * FROM runs WHERE id = ?", (run_id,))
    if row:
        row["steps"] = json.loads(row["steps"] or "[]")
    return row


def wait_for(run_id: str, timeout: float = 300) -> dict | None:
    end = time.time() + timeout
    while time.time() < end:
        r = get_run(run_id)
        if r and r["status"] != "running":
            return r
        time.sleep(1)
    return get_run(run_id)


def workflows_with_trigger(kind: str) -> list[tuple[dict, list[dict]]]:
    out = []
    for wf in db.list_workflows():
        if not wf["enabled"]:
            continue
        hits = [n for n in wf["graph"].get("nodes", []) if n["data"].get("blockType") == f"trigger.{kind}"]
        if hits:
            out.append((wf, hits))
    return out
