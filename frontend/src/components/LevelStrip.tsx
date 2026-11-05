import { useEffect, useRef, useState } from "react";
import type { XpSummary } from "../api";

/** Level, progress to next level, and this week vs last week. Flashes "+N XP" when XP goes up. */
export default function LevelStrip({ xp }: { xp: XpSummary }) {
  const prev = useRef<XpSummary | null>(null);
  const [gain, setGain] = useState<{ n: number; levelUp: boolean; key: number } | null>(null);

  useEffect(() => {
    const p = prev.current;
    if (p && xp.xp !== p.xp) {
      setGain({ n: xp.xp - p.xp, levelUp: xp.level > p.level, key: Date.now() });
      const t = window.setTimeout(() => setGain(null), xp.level > p.level ? 4000 : 1800);
      prev.current = xp;
      return () => window.clearTimeout(t);
    }
    prev.current = xp;
  }, [xp]);

  const pct = Math.min(1, xp.into_level / xp.level_size);
  const beat = xp.this_week - xp.last_week;

  return (
    <div className="level-strip">
      <div className="lv-badge">
        <span className="lv-num">{xp.level}</span>
        <span className="lv-label">Level</span>
      </div>
      <div className="lv-body">
        <div className="lv-title">
          {xp.title}
          <span className="muted"> · {xp.xp.toLocaleString()} XP total</span>
        </div>
        <div className="bar lv-bar">
          <div style={{ width: `${pct * 100}%` }} />
        </div>
        <div className="lv-foot">
          <span>
            {Math.round(xp.into_level)} / {xp.level_size} XP to level {xp.level + 1}
          </span>
          <span>
            Today <b>+{xp.today}</b>
          </span>
          <span>
            This week <b>{xp.this_week}</b>
            {" · "}last week {xp.last_week}
            {xp.last_week > 0 && (beat >= 0 ? <b className="beat"> · beating it by {beat}</b> : <span className="behind-wk"> · {-beat} to beat it</span>)}
          </span>
        </div>
      </div>
      {gain && gain.n !== 0 && (
        <div key={gain.key} className={`xp-pop ${gain.n < 0 ? "neg" : ""} ${gain.levelUp ? "levelup" : ""}`}>
          {gain.levelUp ? `Level ${xp.level}! ${xp.title}` : `${gain.n > 0 ? "+" : ""}${gain.n} XP`}
        </div>
      )}
    </div>
  );
}
