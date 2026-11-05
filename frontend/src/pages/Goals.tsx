import { useEffect, useState } from "react";
import { api, type Goal } from "../api";
import Reminders from "../components/Reminders";

const BLANK: Partial<Goal> = { name: "", category: "personal", kind: "number", unit: "min", target: 30, period: "daily", step: 15 };

const IDEAS: Partial<Goal>[] = [
  { name: "Reading", category: "personal", unit: "min", target: 30, period: "daily", step: 10 },
  { name: "Gym", category: "personal", unit: "sessions", target: 4, period: "weekly", step: 1 },
  { name: "Sleep 7h+", category: "personal", kind: "check", period: "daily" },
  { name: "No junk food", category: "personal", kind: "check", period: "daily" },
  { name: "Security+ study", category: "professional", unit: "min", target: 45, period: "daily", step: 15 },
  { name: "Practice questions", category: "professional", unit: "questions", target: 25, period: "daily", step: 5 },
  { name: "TryHackMe rooms", category: "professional", unit: "rooms", target: 2, period: "weekly", step: 1 },
  { name: "Financial literacy", category: "professional", unit: "min", target: 60, period: "weekly", step: 15 },
  { name: "Coding practice", category: "professional", unit: "min", target: 30, period: "daily", step: 15 },
];

export default function Goals() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [edit, setEdit] = useState<Partial<Goal> | null>(null);
  const [err, setErr] = useState("");

  const load = () => api.goals(true).then(setGoals);
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setErr("");
    try {
      // "" / 0 tell the backend to clear deadline fields
      await api.saveGoal({ ...BLANK, ...edit, kind: edit?.kind ?? "number", deadline: edit?.deadline ?? "", total_target: edit?.total_target ?? 0 });
      setEdit(null);
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const active = goals.filter((g) => !g.archived);
  const archived = goals.filter((g) => g.archived);
  const existing = new Set(active.map((g) => g.name.toLowerCase()));

  return (
    <div className="page">
      <div className="kicker">What you're tracking</div>
      <div className="page-head">
        <h1 className="flush">Goals</h1>
        <button className="btn primary" onClick={() => setEdit({ ...BLANK })}>
          New goal +
        </button>
      </div>

      {edit && (
        <section className="goal-form">
          <h3>{edit.id ? "Edit goal" : "New goal"}</h3>
          <div className="form-grid">
            <label className="field span-2">
              <span>Name</span>
              <input autoFocus value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="e.g. Reading" />
            </label>
            <label className="field">
              <span>Category</span>
              <select value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value as Goal["category"] })}>
                <option value="personal">Personal</option>
                <option value="professional">Professional</option>
              </select>
            </label>
            <label className="field">
              <span>Type</span>
              <select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value as Goal["kind"] })}>
                <option value="number">Amount (minutes, sessions…)</option>
                <option value="check">Yes / no checkbox</option>
              </select>
            </label>
            <label className="field">
              <span>Period</span>
              <select value={edit.period} onChange={(e) => setEdit({ ...edit, period: e.target.value as Goal["period"] })}>
                <option value="daily">Every day</option>
                <option value="weekly">Per week</option>
              </select>
            </label>
            {(edit.kind === "number" || edit.period === "weekly") && (
              <label className="field">
                <span>{edit.kind === "check" ? "Days per week" : "Target"}</span>
                <input type="number" min={0} value={edit.target ?? 1} onChange={(e) => setEdit({ ...edit, target: Number(e.target.value) })} />
              </label>
            )}
            {edit.kind === "number" && edit.category === "professional" && (
              <>
                <label className="field">
                  <span>Deadline (optional)</span>
                  <input type="date" value={edit.deadline ?? ""} onChange={(e) => setEdit({ ...edit, deadline: e.target.value })} />
                </label>
                <label className="field">
                  <span>Total needed by deadline ({edit.unit === "min" ? "hours" : edit.unit || "units"})</span>
                  <input
                    type="number"
                    min={0}
                    value={edit.total_target ? (edit.unit === "min" ? edit.total_target / 60 : edit.total_target) : ""}
                    onChange={(e) => {
                      const n = Number(e.target.value);
                      setEdit({ ...edit, total_target: n ? (edit.unit === "min" ? n * 60 : n) : null });
                    }}
                    placeholder={edit.unit === "min" ? "e.g. 50" : ""}
                  />
                </label>
                <label className="field">
                  <span>Count progress from</span>
                  <input type="date" value={edit.start_date ?? ""} onChange={(e) => setEdit({ ...edit, start_date: e.target.value })} />
                </label>
              </>
            )}
            {edit.kind === "number" && (
              <>
                <label className="field">
                  <span>Unit</span>
                  <input value={edit.unit ?? ""} onChange={(e) => setEdit({ ...edit, unit: e.target.value })} placeholder="min, sessions, pages…" />
                </label>
                <label className="field">
                  <span>Quick-add step</span>
                  <input type="number" min={0} value={edit.step ?? 1} onChange={(e) => setEdit({ ...edit, step: Number(e.target.value) })} />
                </label>
              </>
            )}
          </div>
          {err && <div className="error-box">{err}</div>}
          <div className="row">
            <button className="btn primary" onClick={save}>
              Save goal
            </button>
            <button className="btn ghost" onClick={() => setEdit(null)}>
              Cancel
            </button>
          </div>
        </section>
      )}

      {(["personal", "professional"] as const).map((cat) => (
        <section key={cat} className="goal-list">
          <h3>{cat === "personal" ? "Personal" : "Professional"}</h3>
          <table className="table">
            <tbody>
              {active
                .filter((g) => g.category === cat)
                .map((g) => (
                  <tr key={g.id}>
                    <td className="goal-name">{g.name}</td>
                    <td className="muted">
                      {g.kind === "check"
                        ? g.period === "daily"
                          ? "Yes/no, every day"
                          : `Yes/no, ${g.target} days a week`
                        : `${g.target} ${g.unit} / ${g.period === "daily" ? "day" : "week"}`}
                      {g.deadline && g.total_target
                        ? ` · ${g.unit === "min" ? `${g.total_target / 60} h` : `${g.total_target} ${g.unit}`} by ${g.deadline}`
                        : ""}
                    </td>
                    <td className="actions">
                      {g.deadline &&
                        (g.completed_at ? (
                          <button className="btn ghost" onClick={() => api.completeGoal(g.id, false).then(load)} title="Undo">
                            ✓ Completed {g.completed_at}
                          </button>
                        ) : (
                          <button
                            className="btn"
                            onClick={() => confirm(`Mark "${g.name}" as completed? (+500 XP and the Certified badge)`) && api.completeGoal(g.id).then(load)}
                          >
                            Mark completed
                          </button>
                        ))}
                      <button className="btn ghost" onClick={() => setEdit(g)}>
                        Edit
                      </button>
                      <button className="btn ghost danger-text" onClick={() => api.archiveGoal(g.id).then(load)}>
                        Archive
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      ))}

      <Reminders />

      <section>
        <h3>Ideas · click to add</h3>
        <div className="ideas">
          {IDEAS.filter((i) => !existing.has(i.name!.toLowerCase())).map((i) => (
            <button key={i.name} className="idea" onClick={() => setEdit({ ...BLANK, ...i })}>
              <span className="pill">{i.category}</span> {i.name}
            </button>
          ))}
        </div>
      </section>

      {archived.length > 0 && (
        <section>
          <h3>Archived</h3>
          <p className="muted small">Archived goals keep their history. Restore one to track it again.</p>
          <table className="table">
            <tbody>
              {archived.map((g) => (
                <tr key={g.id}>
                  <td>{g.name}</td>
                  <td className="actions">
                    <button className="btn ghost" onClick={() => api.archiveGoal(g.id, false).then(load)}>
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
