import { useEffect, useState } from "react";
import { api } from "./api.js";
import ReviewQueue from "./components/ReviewQueue.jsx";
import UploadClaims from "./components/UploadClaims.jsx";

const TABS = ["Review Queue", "Upload Claims", "Stats"];

export default function App() {
  const [tab, setTab] = useState("Review Queue");
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ db_connected: false }));
  }, []);

  useEffect(() => {
    if (tab === "Stats") {
      api.reviewStats().then(setStats).catch(() => {});
    }
  }, [tab]);

  return (
    <div className="app">
      <div className="header">
        <h1>Healthcare Fraud Detection</h1>
        {health && (
          <span style={{ fontSize: 12, color: "#94a3b8", marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
            <span className={`status-dot ${health.db_connected ? "" : "offline"}`} />
            {health.db_connected ? "Connected" : "DB offline"}
          </span>
        )}
      </div>

      <div className="nav">
        {TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      <div className="main">
        {tab === "Review Queue" && <ReviewQueue />}
        {tab === "Upload Claims" && <UploadClaims onUploaded={() => setTab("Review Queue")} />}
        {tab === "Stats" && <StatsView stats={stats} />}
      </div>
    </div>
  );
}

function StatsView({ stats }) {
  if (!stats) return <div className="loading">Loading stats...</div>;

  return (
    <div>
      <div className="stats-row">
        <div className="stat-card"><div className="num">{stats.total_claims}</div><div className="label">Total Claims</div></div>
        <div className="stat-card"><div className="num">{stats.total_analyzed}</div><div className="label">Analyzed</div></div>
        <div className="stat-card"><div className="num">{stats.total_reviewed}</div><div className="label">Reviewed (Labels)</div></div>
        <div className="stat-card"><div className="num">{stats.label_coverage_pct}%</div><div className="label">Label Coverage</div></div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card">
          <div className="card-title">By Risk Level</div>
          {Object.entries(stats.by_risk_level).length === 0
            ? <div style={{ color: "#94a3b8" }}>No data yet</div>
            : Object.entries(stats.by_risk_level).map(([level, count]) => (
                <div key={level} style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span className={`risk-badge ${level}`}>{level}</span>
                  <strong>{count}</strong>
                </div>
              ))}
        </div>

        <div className="card">
          <div className="card-title">Investigator Decisions</div>
          {Object.entries(stats.by_decision).length === 0
            ? <div style={{ color: "#94a3b8" }}>No reviews yet — label your first claims to build the dataset</div>
            : Object.entries(stats.by_decision).map(([decision, count]) => (
                <div key={decision} style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontSize: 13 }}>{decision.replace(/_/g, " ")}</span>
                  <strong>{count}</strong>
                </div>
              ))}
          {Object.values(stats.by_decision).reduce((a, b) => a + b, 0) < 500 && (
            <div style={{ marginTop: 12, fontSize: 12, color: "#64748b", background: "#f8fafc", padding: 8, borderRadius: 6 }}>
              Phase 2 ML training unlocks at ~500 labeled reviews.
              Current: <strong>{Object.values(stats.by_decision).reduce((a, b) => a + b, 0)}</strong> / 500
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
