import { useEffect, useState } from "react";
import { api, type NotifyStatus } from "../api";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const fmtNext = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" }) : "—";

/** Discord reminder settings with test / preview buttons. */
export default function Reminders() {
  const [st, setSt] = useState<NotifyStatus | null>(null);
  const [s, setS] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.notify().then((r) => (setSt(r), setS(r.settings))).catch(() => {});
  }, []);

  if (!st) return null;
  const set = (k: string, v: string) => setS({ ...s, [k]: v });
  const save = async () => {
    const r = await api.saveNotify(s);
    setSt(r);
    setMsg("Saved");
    setTimeout(() => setMsg(""), 1500);
  };
  const send = async (kind: string) => {
    setMsg("Sending…");
    try {
      const r = await api.sendNotify(kind);
      setMsg(r.result === "sent" ? "Sent - check Discord" : r.result);
    } catch (e: any) {
      setMsg(e.message);
    }
  };

  return (
    <section className="reminders">
      <h3>Reminders · Discord</h3>
      {!st.configured ? (
        <div className="error-box">
          Not connected yet. Add <code>DISCORD_WEBHOOK_URL=…</code> to <code>~/docker/sims-tracker/.env</code> on the Pi, then run{" "}
          <code>docker compose up -d</code> in that folder.
        </div>
      ) : (
        <p className="muted small">
          Connected{st.mention ? " · @mentions you" : " · add DISCORD_USER_ID to .env to get @mentioned"}. Nudges only fire when there's
          something to say.
        </p>
      )}

      <table className="table reminder-table">
        <tbody>
          <tr>
            <td>
              <b>Behind today</b>
              <div className="muted small">Lists goals still open, plus cert pace if you're behind. Skipped if you're done.</div>
            </td>
            <td>
              <input type="time" value={s.notify_behind_at ?? ""} onChange={(e) => set("notify_behind_at", e.target.value)} />
            </td>
            <td className="muted small">Next: {fmtNext(st.next_runs.behind)}</td>
            <td className="actions">
              <button className="btn ghost" onClick={() => send("behind")} disabled={!st.configured}>Preview</button>
            </td>
          </tr>
          <tr>
            <td>
              <b>Streak at risk</b>
              <div className="muted small">Any daily streak of 3+ days that ends at midnight unless you log.</div>
            </td>
            <td>
              <input type="time" value={s.notify_streak_at ?? ""} onChange={(e) => set("notify_streak_at", e.target.value)} />
            </td>
            <td className="muted small">Next: {fmtNext(st.next_runs.streak)}</td>
            <td className="actions">
              <button className="btn ghost" onClick={() => send("streak")} disabled={!st.configured}>Preview</button>
            </td>
          </tr>
          <tr>
            <td>
              <b>Weekly scorecard</b>
              <div className="muted small">XP vs last week, goals hit, streaks, cert pace, new badges.</div>
            </td>
            <td className="row">
              <select value={s.notify_weekly_day ?? "sun"} onChange={(e) => set("notify_weekly_day", e.target.value)} style={{ width: 80 }}>
                {DAYS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <input type="time" value={s.notify_weekly_at ?? ""} onChange={(e) => set("notify_weekly_at", e.target.value)} />
            </td>
            <td className="muted small">Next: {fmtNext(st.next_runs.weekly)}</td>
            <td className="actions">
              <button className="btn ghost" onClick={() => send("weekly")} disabled={!st.configured}>Preview</button>
            </td>
          </tr>
          <tr>
            <td>
              <b>Level-ups &amp; badges</b>
              <div className="muted small">Announced within 5 minutes of earning them.</div>
            </td>
            <td className="muted small">automatic</td>
            <td />
            <td />
          </tr>
        </tbody>
      </table>

      <div className="row">
        <label className="check">
          <input type="checkbox" checked={s.notify_enabled === "true"} onChange={(e) => set("notify_enabled", e.target.checked ? "true" : "false")} />
          Reminders on
        </label>
        <button className="btn primary" onClick={save}>
          Save reminder times
        </button>
        <button className="btn" onClick={() => send("test")} disabled={!st.configured}>
          Send test message
        </button>
        {msg && <span className="muted small">{msg}</span>}
      </div>
    </section>
  );
}
