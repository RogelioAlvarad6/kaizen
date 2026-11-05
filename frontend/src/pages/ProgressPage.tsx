import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type GoalStats, type XpSummary } from "../api";
import { BurnUp, GoalBars, Heatmap, HeatLegend, shortDay } from "../components/Charts";
import { amount, fmtDate } from "../components/Pace";

type Filter = "all" | "personal" | "professional";
const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

export default function ProgressPage() {
  const [stats, setStats] = useState<GoalStats[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const [xp, setXp] = useState<XpSummary | null>(null);

  useEffect(() => {
    api.stats(84).then((r) => setStats(r.goals));
    api.xp().then(setXp).catch(() => {});
  }, []);

  const shown = useMemo(() => (stats ?? []).filter((s) => filter === "all" || s.goal.category === filter), [stats, filter]);

  // Overall discipline: share of daily goals met, per day, last 30 days
  const overall = useMemo(() => {
    const dailies = shown.filter((s) => s.goal.period === "daily");
    if (!dailies.length) return [];
    const days = dailies[0].daily.slice(-30).map((d) => d.day);
    return days.map((day, i) => {
      const met = dailies.filter((s) => {
        const v = s.daily[s.daily.length - 30 + i]?.value ?? 0;
        return v >= s.goal.target;
      }).length;
      return { key: day, label: shortDay(day), value: Math.round((100 * met) / dailies.length) };
    });
  }, [shown]);

  if (!stats) return <div className="page">Loading…</div>;
  if (stats.length === 0)
    return (
      <div className="page">
        <h1>Progress</h1>
        <Link className="btn primary" to="/goals">Add a goal first →</Link>
      </div>
    );

  return (
    <div className="page">
      <div className="kicker">Last 12 weeks</div>
      <div className="page-head">
        <h1 className="flush">Progress</h1>
        <div className="seg" role="tablist">
          {(["all", "personal", "professional"] as Filter[]).map((f) => (
            <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)} role="tab" aria-selected={filter === f}>
              {f === "all" ? "All" : f === "personal" ? "Personal" : "Professional"}
            </button>
          ))}
        </div>
      </div>

      {/* summary row: one big number per goal */}
      <div className="streak-row" style={{ gridTemplateColumns: `repeat(${Math.min(4, shown.length)}, minmax(0, 1fr))` }}>
        {shown.map((s) => (
          <div key={s.goal.id} className="streak">
            <div className="goal-label">{s.goal.name}</div>
            <div className="streak-num">
              {s.streak.current}
              <span>{s.streak.unit} streak</span>
            </div>
            <div className="muted small">
              Best {s.streak.best} · hit {s.streak.rate}% of last {s.streak.window}
            </div>
          </div>
        ))}
      </div>

      {xp && filter === "all" && (
        <section className="xp-section">
          <h3>Points &amp; levels · Level {xp.level} {xp.title} · {xp.xp.toLocaleString()} XP</h3>
          <div className="two-col">
            <div>
              <div className="muted small">XP earned per day (red line = a perfect day: every daily goal met)</div>
              <GoalBars
                unit="XP"
                goal={xp.perfect_day_xp || 40}
                height={130}
                data={xp.daily.map((d) => ({ key: d.day, label: shortDay(d.day), value: d.xp }))}
              />
            </div>
            <div>
              <div className="muted small">Recent XP</div>
              <ul className="xp-log">
                {xp.recent.slice(0, 8).map((e, i) => (
                  <li key={i}>
                    <span className="muted">{shortDay(e.day)}</span>
                    <span>
                      {e.goal ? <b>{e.goal}</b> : null} {e.reason}
                    </span>
                    <span className="xp-amt">+{e.xp}</span>
                  </li>
                ))}
                {xp.recent.length === 0 && <li className="muted">Log something on Today to earn your first XP.</li>}
              </ul>
            </div>
          </div>

          <h3>Badges · {xp.badges.filter((b) => b.earned_on).length} of {xp.badges.length}</h3>
          <div className="badges">
            {xp.badges.map((b) => (
              <div key={b.key} className={`badge ${b.earned_on ? "earned" : ""}`} title={b.desc}>
                <div className="badge-mark" />
                <div className="badge-name">{b.name}</div>
                <div className="badge-desc">{b.desc}</div>
                {b.earned_on && <div className="badge-date">Earned {shortDay(b.earned_on)}</div>}
              </div>
            ))}
          </div>

          <p className="xp-rules">
            How XP works: daily goal met <b>+10</b> (partial <b>+5</b>) · perfect day <b>+20</b> · weekly goal met <b>+50</b> (each day you
            show up <b>+3</b>) · streaks: 7 days <b>+50</b>, 30 days <b>+200</b>, 100 days <b>+1000</b>, 4 weeks <b>+100</b>, 12 weeks{" "}
            <b>+400</b> · complete a certification <b>+500</b>. XP is recalculated from your logs, so fixing a past day updates it.
          </p>
        </section>
      )}

      {overall.length > 0 && (
        <section className="overall">
          <h3>Daily discipline · % of daily goals met</h3>
          <GoalBars unit="%" goal={100} max={100} data={overall} height={130} />
        </section>
      )}

      {shown.map((s) => {
        const g = s.goal;
        const dailyTarget = g.period === "daily" ? g.target : g.target / 7;
        const isCheckDaily = g.kind === "check" && g.period === "daily";
        return (
          <section key={g.id} className="goal-section">
            <div className="goal-section-head">
              <h3 className="flush">{g.name}</h3>
              <span className="pill">{g.category}</span>
              <span className="muted small grow-right">
                {g.kind === "check"
                  ? `Goal: ${g.period === "daily" ? "every day" : `${fmt(g.target)} days / week`} · done ${fmt(s.total_30)} of the last 30 days`
                  : `Goal: ${fmt(g.target)} ${g.unit} / ${g.period === "daily" ? "day" : "week"} · last 30 days total: ${fmt(s.total_30)} ${g.unit}`}
              </span>
            </div>
            {s.burnup && s.pace && (
              <div className="burnup">
                <div className="muted small">
                  Toward {amount(s.pace.total, g.unit)} by {fmtDate(s.pace.deadline)} · {amount(s.pace.done, g.unit)} done ·{" "}
                  {s.pace.status === "behind" ? `behind by ${amount(s.pace.gap_per_day, g.unit)}/day` : s.pace.status.replace("_", " ")}
                </div>
                <BurnUp points={s.burnup} fmt={(v) => amount(v, g.unit)} />
              </div>
            )}
            <div className="goal-charts">
              <Heatmap label="Consistency" unit={g.unit} goal={dailyTarget} cells={s.daily} />
              <div className="goal-bars">
                {isCheckDaily ? (
                  <GoalBars
                    unit="days"
                    goal={7}
                    max={7}
                    height={140}
                    data={s.weekly.map((w) => ({ key: w.week, label: `wk ${shortDay(w.week)}`, value: w.value }))}
                  />
                ) : g.period === "daily" ? (
                  <GoalBars unit={g.unit} goal={g.target} height={140} data={s.daily.slice(-30).map((d) => ({ key: d.day, label: shortDay(d.day), value: d.value }))} />
                ) : (
                  <GoalBars unit={g.unit} goal={g.target} height={140} data={s.weekly.map((w) => ({ key: w.week, label: `wk ${shortDay(w.week)}`, value: w.value }))} />
                )}
              </div>
            </div>
          </section>
        );
      })}
      <HeatLegend />
    </div>
  );
}
