import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Workflow } from "../api";

const TRIGGER_ICONS: Record<string, string> = {
  "trigger.manual": "Manual",
  "trigger.chat": "Chat",
  "trigger.schedule": "Cron",
  "trigger.folder": "Folder",
};

export default function Workflows() {
  const [list, setList] = useState<Workflow[]>([]);
  useEffect(() => {
    api.workflows().then(setList);
  }, []);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="kicker">Behind the scenes</div>
          <h1>Automations</h1>
        </div>
        <Link to="/workflows/new" className="btn primary">
          New workflow +
        </Link>
      </div>
      <div className="cards">
        {list.map((w, i) => {
          const triggers = w.graph.nodes.filter((n: any) => n.data.blockType.startsWith("trigger."));
          return (
            <Link key={w.id} to={`/workflows/${w.id}`} className={`card ${w.enabled ? "" : "disabled"}`}>
              <div className="card-num">{String(i + 1).padStart(2, "0")}</div>
              <div className="card-title">{w.name}</div>
              <p className="muted small">{w.description}</p>
              <div className="card-foot">
                {triggers.map((t: any) => (
                  <span key={t.id} className="pill" title={t.data.label}>
                    {TRIGGER_ICONS[t.data.blockType]}
                    {t.data.config?.cron ? ` ${t.data.config.cron}` : ""}
                  </span>
                ))}
                <span className="muted small grow-right">{w.graph.nodes.length} blocks</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

