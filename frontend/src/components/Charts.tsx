import { useState } from "react";

/* Single-series charts in the Swiss style: ink on paper, one hue, lightness = progress.
   Every chart has a hover tooltip; values never rely on color alone (goal line + tooltip text). */

const INK = "#111111";
const BELOW = "#b9b9b3"; // bar below goal
const HEAT = ["#e7e7e2", "#cfcfc9", "#9b9b95", "#111111"]; // none, <50%, <100%, goal met

const fmtDay = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

type Tip = { x: number; y: number; title: string; body: string } | null;

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="chart-tip" style={{ left: tip.x, top: tip.y }}>
      <div className="chart-tip-title">{tip.title}</div>
      <div>{tip.body}</div>
    </div>
  );
}

/* ---------------- bar chart with goal line ---------------- */
type Bar = { key: string; label: string; value: number };

export function GoalBars({ data, goal, unit, height = 150, max: fixedMax }: { data: Bar[]; goal: number; unit: string; height?: number; max?: number }) {
  const [tip, setTip] = useState<Tip>(null);
  const [hover, setHover] = useState<string | null>(null);
  const W = 640;
  const H = height;
  const pad = { l: 28, r: 8, t: 12, b: 22 };
  const max = fixedMax ?? Math.max(goal * 1.25, ...data.map((d) => d.value), 1);
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const step = iw / data.length;
  const bw = Math.max(2, step - 2); // 2px surface gap between bars
  const y = (v: number) => pad.t + ih - (v / max) * ih;
  const r = Math.min(4, bw / 2);

  const barPath = (x: number, top: number, w: number) => {
    const base = pad.t + ih;
    const h = base - top;
    if (h <= 0) return "";
    const rr = Math.min(r, h);
    return `M${x},${base} V${top + rr} Q${x},${top} ${x + rr},${top} H${x + w - rr} Q${x + w},${top} ${x + w},${top + rr} V${base} Z`;
  };

  const labelIdx = new Set([0, Math.floor(data.length / 2), data.length - 1]);

  return (
    <div className="chart" onMouseLeave={() => (setTip(null), setHover(null))}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Bar chart, goal ${goal} ${unit}`}>
        {/* recessive baseline + max tick */}
        <line x1={pad.l} x2={W - pad.r} y1={pad.t + ih} y2={pad.t + ih} stroke="#cfcfc9" />
        <text x={pad.l - 6} y={pad.t + ih} className="axis" textAnchor="end" dominantBaseline="middle">0</text>
        <text x={pad.l - 6} y={y(max)} className="axis" textAnchor="end" dominantBaseline="middle">{Math.round(max)}</text>
        {data.map((d, i) => {
          const x = pad.l + i * step + 1;
          const met = d.value >= goal;
          return (
            <g key={d.key}>
              <path d={barPath(x, y(d.value), bw)} fill={met ? INK : BELOW} opacity={hover && hover !== d.key ? 0.45 : 1} />
              {labelIdx.has(i) && (
                <text x={x + bw / 2} y={H - 6} className="axis" textAnchor={i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"}>
                  {d.label}
                </text>
              )}
              {/* hit target: the whole column, bigger than the mark */}
              <rect
                x={pad.l + i * step}
                y={pad.t}
                width={step}
                height={ih}
                fill="transparent"
                onMouseMove={(e) => {
                  const box = (e.currentTarget.ownerSVGElement!.parentElement as HTMLElement).getBoundingClientRect();
                  setHover(d.key);
                  setTip({
                    x: e.clientX - box.left,
                    y: e.clientY - box.top,
                    title: d.label,
                    body: `${d.value} ${unit} · ${met ? "goal met" : `${Math.max(0, goal - d.value)} ${unit} short`}`,
                  });
                }}
              />
            </g>
          );
        })}
        {/* goal line, drawn over the bars */}
        <line x1={pad.l} x2={W - pad.r} y1={y(goal)} y2={y(goal)} stroke="#e30613" strokeWidth={1.25} strokeDasharray="4 3" pointerEvents="none" />
      </svg>
      <div className="chart-legend">
        <span><i className="lg-goal" /> Goal {goal} {unit}</span>
        <span><i className="lg-met" /> Goal met</span>
        <span><i className="lg-below" /> Below goal</span>
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}

/* ---------------- consistency heatmap (weeks × weekdays) ---------------- */
type Cell = { day: string; value: number };

export function Heatmap({ cells, goal, unit, label }: { cells: Cell[]; goal: number; unit: string; label: string }) {
  const [tip, setTip] = useState<Tip>(null);
  const size = 13;
  const gap = 3;
  // pad the front so columns start on Monday
  const first = new Date(cells[0]?.day + "T12:00:00");
  const lead = (first.getDay() + 6) % 7;
  const grid: (Cell | null)[] = [...Array(lead).fill(null), ...cells];
  const weeks = Math.ceil(grid.length / 7);
  const today = cells[cells.length - 1]?.day;
  const level = (v: number) => (v <= 0 ? 0 : v >= goal ? 3 : v >= goal / 2 ? 2 : 1);
  const W = weeks * (size + gap) + 18;
  const H = 7 * (size + gap);

  return (
    <div className="chart heatmap" onMouseLeave={() => setTip(null)}>
      <div className="heat-label">{label}</div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${label} consistency heatmap`}>
        {["M", "", "W", "", "F", "", "S"].map((d, i) => (
          <text key={i} x={0} y={i * (size + gap) + size - 2} className="axis">{d}</text>
        ))}
        {grid.map((c, i) => {
          if (!c) return null;
          const col = Math.floor(i / 7);
          const row = i % 7;
          const x = 18 + col * (size + gap);
          const yy = row * (size + gap);
          return (
            <rect
              key={c.day}
              x={x}
              y={yy}
              width={size}
              height={size}
              fill={HEAT[level(c.value)]}
              stroke={c.day === today ? "#e30613" : "none"}
              strokeWidth={c.day === today ? 1.5 : 0}
              onMouseMove={(e) => {
                const box = (e.currentTarget.ownerSVGElement!.parentElement as HTMLElement).getBoundingClientRect();
                setTip({
                  x: e.clientX - box.left,
                  y: e.clientY - box.top,
                  title: fmtDay(c.day),
                  body: `${c.value} ${unit}${c.value >= goal ? " · goal met" : ""}`,
                });
              }}
            />
          );
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

export function HeatLegend() {
  return (
    <div className="heat-legend">
      <span>None</span>
      {HEAT.map((c) => (
        <i key={c} style={{ background: c }} />
      ))}
      <span>Goal met</span>
      <span className="muted">· red outline = today</span>
    </div>
  );
}

/* ---------------- burn-up: cumulative actual vs. straight-line plan to a deadline ---------------- */
type BurnPoint = { day: string; actual: number | null; plan: number };

export function BurnUp({ points, fmt }: { points: BurnPoint[]; fmt: (v: number) => string }) {
  const [hi, setHi] = useState<number | null>(null);
  const W = 640;
  const H = 180;
  const pad = { l: 44, r: 12, t: 12, b: 22 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const max = Math.max(...points.map((p) => Math.max(p.plan, p.actual ?? 0)), 1);
  const x = (i: number) => pad.l + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
  const y = (v: number) => pad.t + ih - (v / max) * ih;
  const line = (vals: (number | null)[]) =>
    vals.map((v, i) => (v == null ? "" : `${i === 0 || vals[i - 1] == null ? "M" : "L"}${x(i)},${y(v)}`)).join(" ");
  const actual = points.map((p) => p.actual);
  const lastActual = actual.reduce<number>((acc, v, i) => (v != null ? i : acc), -1);
  const h = hi != null ? points[hi] : null;

  return (
    <div className="chart" onMouseLeave={() => setHi(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Cumulative progress versus plan">
        <line x1={pad.l} x2={W - pad.r} y1={pad.t + ih} y2={pad.t + ih} stroke="#cfcfc9" />
        <text x={pad.l - 6} y={pad.t + ih} className="axis" textAnchor="end" dominantBaseline="middle">0</text>
        <text x={pad.l - 6} y={y(max)} className="axis" textAnchor="end" dominantBaseline="middle">{fmt(max)}</text>
        <text x={pad.l} y={H - 6} className="axis">{shortDay(points[0].day)}</text>
        <text x={W - pad.r} y={H - 6} className="axis" textAnchor="end">{shortDay(points[points.length - 1].day)}</text>
        <path d={line(points.map((p) => p.plan))} fill="none" stroke="#e30613" strokeWidth={1.5} strokeDasharray="5 4" />
        <path d={line(actual)} fill="none" stroke="#111" strokeWidth={2} />
        {lastActual >= 0 && (
          <circle cx={x(lastActual)} cy={y(actual[lastActual]!)} r={4} fill="#111" stroke="#fff" strokeWidth={2} />
        )}
        {hi != null && <line x1={x(hi)} x2={x(hi)} y1={pad.t} y2={pad.t + ih} stroke="#111" strokeOpacity={0.25} />}
        {points.map((p, i) => (
          <rect
            key={p.day}
            x={x(i) - iw / points.length / 2}
            y={pad.t}
            width={iw / points.length}
            height={ih}
            fill="transparent"
            onMouseMove={() => setHi(i)}
          />
        ))}
      </svg>
      {h && (
        <div className="chart-tip" style={{ left: `${(x(hi!) / W) * 100}%`, top: 8 }}>
          <div className="chart-tip-title">{fmtDay(h.day)}</div>
          <div>Done: {h.actual == null ? "—" : fmt(h.actual)}</div>
          <div>Plan: {fmt(h.plan)}</div>
        </div>
      )}
      <div className="chart-legend">
        <span><i className="lg-actual" /> Your total</span>
        <span><i className="lg-goal" /> Plan to finish on time</span>
      </div>
    </div>
  );
}

export const shortDay = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
