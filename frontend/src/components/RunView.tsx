import { useState } from "react";
import type { Run } from "../api";
import Markdown from "./Markdown";

export default function RunView({ run }: { run: Run }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="run-view">
      <div className="run-head">
        <span className={`pill pill-${run.status}`}>{run.status}</span>
        <span className="muted small">
          {run.workflow_name} · {run.trigger} · {run.started_at?.replace("T", " ")} · ${run.cost_usd?.toFixed(4)}
        </span>
      </div>
      {run.error && <div className="error-box">{run.error}</div>}
      <ol className="steps">
        {(run.steps ?? []).map((s) => (
          <li key={s.node_id} className={`step step-${s.status}`}>
            <button className="step-head" onClick={() => setOpen(open === s.node_id ? null : s.node_id)}>
              <span className={`dot dot-${s.status}`} />
              <b>{s.label}</b>
              <code className="small">{s.node_id}</code>
              {s.branch && <span className="pill">→ {s.branch}</span>}
              <span className="muted small grow-right">
                {s.seconds != null ? `${s.seconds}s` : "…"} {s.cost ? `· $${s.cost.toFixed(4)}` : ""}
              </span>
            </button>
            {(open === s.node_id || s.status === "running") && (
              <div className="step-body">
                {s.events && s.events.length > 0 && (
                  <pre className="events">{s.events.join("\n")}</pre>
                )}
                {s.error && <div className="error-box">{s.error}</div>}
                {s.output && <Markdown text={s.output} />}
              </div>
            )}
          </li>
        ))}
      </ol>
      {run.status === "success" && run.output && (
        <div className="final-output">
          <div className="muted small">Final output</div>
          <Markdown text={run.output} />
        </div>
      )}
    </div>
  );
}
