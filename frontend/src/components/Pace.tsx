import type { Goal, Pace } from "../api";

/** Formats an amount in the goal's unit; minutes become "1h 55m". */
export function amount(v: number, unit: string) {
  if (unit === "min") {
    const m = Math.round(v);
    if (m < 60) return `${m}m`;
    return `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}`;
  }
  return `${Number.isInteger(v) ? v : v.toFixed(1)} ${unit}`;
}

export const fmtDate = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });

const STATUS: Record<Pace["status"], string> = {
  on_pace: "On pace",
  behind: "Behind pace",
  done: "Target reached",
  overdue: "Past deadline",
  completed: "Completed",
};

/** Big countdown card shown at the top of Today for goals with a deadline. */
export function DeadlineCard({ g, p }: { g: Goal; p: Pace }) {
  const pct = Math.min(1, p.done / p.total);
  const total = g.unit === "min" ? `${Math.round(p.total / 60)}h` : amount(p.total, g.unit);
  return (
    <div className={`deadline-card status-${p.status}`}>
      <div className="dl-left">
        <div className="dl-days">{Math.max(0, p.days_left)}</div>
        <div className="dl-days-label">{p.days_left === 1 ? "day left" : "days left"}</div>
      </div>
      <div className="dl-body">
        <div className="dl-title">
          {g.name} <span className="muted">· by {fmtDate(p.deadline)}</span>
        </div>
        <div className="bar">
          <div style={{ width: `${pct * 100}%` }} />
        </div>
        <div className="dl-stats">
          <span>
            <b>{amount(p.done, g.unit)}</b> of {total} done
          </span>
          <span>
            Need <b>{amount(p.need_per_day, g.unit)}</b>/day
          </span>
          <span>
            Your 14-day avg <b>{amount(p.avg_per_day, g.unit)}</b>/day
          </span>
          <span className={`dl-status ${p.status}`}>
            {STATUS[p.status]}
            {p.status === "behind" ? ` by ${amount(p.gap_per_day, g.unit)}/day` : ""}
          </span>
        </div>
      </div>
    </div>
  );
}
