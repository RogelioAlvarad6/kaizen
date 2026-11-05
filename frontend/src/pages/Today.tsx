import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DayGoal, type GoalStats, type XpSummary } from "../api";
import { DeadlineCard } from "../components/Pace";
import LevelStrip from "../components/LevelStrip";

export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (day: string, n: number) => {
  const d = new Date(day + "T12:00:00");
  d.setDate(d.getDate() + n);
  return iso(d);
};
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const fmtNum = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

export default function Today() {
  const todayIso = iso(new Date());
  const [day, setDay] = useState(todayIso);
  const [goals, setGoals] = useState<DayGoal[] | null>(null);
  const [stats, setStats] = useState<GoalStats[]>([]);
  const [err, setErr] = useState("");
  const [xp, setXp] = useState<XpSummary | null>(null);

  const load = (d = day) => {
    api.day(d).then((r) => setGoals(r.goals)).catch((e) => setErr(e.message));
    api.stats(28).then((r) => setStats(r.goals)).catch(() => {});
    api.xp().then(setXp).catch(() => {});
  };
  useEffect(() => load(day), [day]);

  const save = async (g: DayGoal, value: number, note?: string) => {
    value = Math.max(0, Math.round(value * 100) / 100);
    // optimistic update so the UI feels instant
    setGoals((gs) =>
      gs!.map((x) => {
        if (x.id !== g.id) return x;
        const progress = x.period === "weekly" ? x.progress - x.value + value : value;
        return { ...x, value, note: note ?? x.note, progress, met: progress >= x.target };
      })
    );
    await api.log(g.id, day, value, note);
    load(day);
  };

  if (err) return <div className="page"><div className="error-box">Backend not reachable: {err}. Start it with start.cmd.</div></div>;
  if (!goals) return <div className="page">Loading…</div>;

  const done = goals.filter((g) => g.met).length;
  const isToday = day === todayIso;
  const groups = (["personal", "professional"] as const).map((c) => ({ cat: c, list: goals.filter((g) => g.category === c) }));
  const last7 = Array.from({ length: 7 }, (_, i) => addDays(todayIso, i - 6));

  return (
    <div className="page today">
      <div className="day-nav">
        <button className="btn ghost" onClick={() => setDay(addDays(day, -1))} aria-label="Previous day">
          ←
        </button>
        <span className="kicker flush">
          {new Date(day + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          {isToday ? " · Today" : ""}
        </span>
        <button className="btn ghost" onClick={() => setDay(addDays(day, 1))} disabled={isToday} aria-label="Next day">
          →
        </button>
        {!isToday && (
          <button className="btn ghost" onClick={() => setDay(todayIso)}>
            Back to today
          </button>
        )}
      </div>
      <h1>
        {goals.length === 0 ? "Add your first goal." : done === goals.length ? "All goals hit." : `${done} of ${goals.length} done.`}
      </h1>

      {goals.length === 0 && (
        <p>
          <Link className="btn primary" to="/goals">Set up goals →</Link>
        </p>
      )}

      {/* wide screens: level + deadlines side by side, then Personal | Professional columns */}
      <div className="today-top">
        {xp && <LevelStrip xp={xp} />}
        {goals.some((g) => g.pace) && (
          <section className="deadlines">
            {goals.filter((g) => g.pace).map((g) => (
              <DeadlineCard key={g.id} g={g} p={g.pace!} />
            ))}
          </section>
        )}
      </div>

      <div className="today-groups">
        {groups.map(
          ({ cat, list }) =>
            list.length > 0 && (
              <section key={cat} className="goal-group">
                <h3>{cat === "personal" ? "Personal" : "Professional"}</h3>
                {list.map((g) => (
                  <GoalRow key={`${g.id}-${day}`} g={g} onSave={save} />
                ))}
              </section>
            )
        )}
      </div>

      {stats.length > 0 && (
        <section className="week">
          <h3>Last 7 days</h3>
          <table className="week-grid">
            <thead>
              <tr>
                <th />
                {last7.map((d) => (
                  <th key={d} className={d === day ? "is-today" : ""}>
                    {WEEKDAYS[(new Date(d + "T12:00:00").getDay() + 6) % 7]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => {
                const dailyTarget = s.goal.period === "daily" ? s.goal.target : s.goal.target / 7;
                const byDay = Object.fromEntries(s.daily.map((x) => [x.day, x.value]));
                return (
                  <tr key={s.goal.id}>
                    <td className="week-kind">{s.goal.name}</td>
                    {last7.map((d) => {
                      const v = byDay[d] ?? 0;
                      const cls = v >= dailyTarget && v > 0 ? "met" : v > 0 ? "partial" : "";
                      return (
                        <td key={d} title={`${d}: ${fmtNum(v)} ${s.goal.unit}`}>
                          <button className={`sq ${cls}`} onClick={() => setDay(d)} aria-label={`${s.goal.name} on ${d}`} />
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="week-foot">
            <span><i className="sq met" /> goal met</span>
            <span><i className="sq partial" /> some progress</span>
            <span><i className="sq" /> nothing</span>
            <Link to="/progress" className="more">See charts →</Link>
          </div>
        </section>
      )}
    </div>
  );
}

function GoalRow({ g, onSave }: { g: DayGoal; onSave: (g: DayGoal, v: number, note?: string) => void }) {
  const [val, setVal] = useState(String(g.value));
  const [note, setNote] = useState(g.note);
  const pct = Math.min(1, g.progress / g.target);
  const targetText =
    g.kind === "check"
      ? g.period === "daily"
        ? "daily"
        : `${fmtNum(g.progress)} / ${fmtNum(g.target)} days this week`
      : g.period === "daily"
        ? `${fmtNum(g.progress)} / ${fmtNum(g.target)} ${g.unit}`
        : `${fmtNum(g.progress)} / ${fmtNum(g.target)} ${g.unit} this week`;

  return (
    <div className={`goal-row ${g.met ? "met" : ""}`}>
      <div className="goal-info">
        <div className="goal-name">{g.name}</div>
        <div className="goal-target">{targetText}</div>
        <div className="bar">
          <div style={{ width: `${pct * 100}%` }} />
        </div>
      </div>

      <div className="goal-input">
        {g.kind === "check" ? (
          <button className={`check-btn ${g.value >= 1 ? "on" : ""}`} onClick={() => onSave(g, g.value >= 1 ? 0 : 1)}>
            {g.value >= 1 ? "✓ Done" : "Mark done"}
          </button>
        ) : (
          <>
            <button className="btn step" onClick={() => (setVal(String(Math.max(0, g.value - g.step))), onSave(g, g.value - g.step))} aria-label="Decrease">
              −
            </button>
            <input
              className="num"
              inputMode="decimal"
              value={val}
              onChange={(e) => setVal(e.target.value)}
              onBlur={() => Number(val) !== g.value && onSave(g, Number(val) || 0)}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
              aria-label={`${g.name} ${g.unit}`}
            />
            <span className="unit">{g.unit}</span>
            <button className="btn step" onClick={() => (setVal(String(g.value + g.step)), onSave(g, g.value + g.step))}>
              +{fmtNum(g.step)}
            </button>
          </>
        )}
      </div>

      <input
        className="goal-note"
        placeholder="note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => note !== g.note && onSave(g, g.value, note)}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
    </div>
  );
}
