import { useEffect, useState } from "react";
import { api, type Run } from "../api";
import RunView from "../components/RunView";

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [sel, setSel] = useState<Run | null>(null);

  useEffect(() => {
    const load = () => api.runs().then(setRuns);
    load();
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="page runs-page">
      <div className="kicker">Behind the scenes</div>
      <h1>History</h1>
      <div className="two-col">
        <table className="table clickable">
          <thead>
            <tr>
              <th>Started</th>
              <th>Workflow</th>
              <th>Trigger</th>
              <th>Status</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} onClick={() => api.run(r.id).then(setSel)} className={sel?.id === r.id ? "active" : ""}>
                <td>{r.started_at.replace("T", " ")}</td>
                <td>{r.workflow_name}</td>
                <td>{r.trigger}</td>
                <td>
                  <span className={`pill pill-${r.status}`}>{r.status}</span>
                </td>
                <td>${r.cost_usd.toFixed(4)}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No runs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="panel">{sel ? <RunView run={sel} /> : <p className="muted">Select a run to see each step.</p>}</div>
      </div>
    </div>
  );
}

