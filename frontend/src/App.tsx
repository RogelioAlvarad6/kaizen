import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import Today from "./pages/Today";
import ProgressPage from "./pages/ProgressPage";
import Goals from "./pages/Goals";

// The app is a daily goal tracker for now. The AI pages (Chat, Automations, History) are parked
// in src/pages and can be re-added to the routes later.
const NAV = [
  { to: "/", label: "Today" },
  { to: "/progress", label: "Progress" },
  { to: "/goals", label: "Goals" },
];

export default function App() {
  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">
          <span className="brand-mark" />
          <span className="brand-text">
            Kaizen
            <span className="brand-sub">改善 · 1% better daily</span>
          </span>
        </div>
        {NAV.map((n, i) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}>
            <span className="nav-num">{String(i + 1).padStart(2, "0")}</span>
            <span className="nav-label">{n.label}</span>
          </NavLink>
        ))}
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
