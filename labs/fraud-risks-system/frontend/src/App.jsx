import { useEffect, useState } from "react";
import { api } from "./api.js";
import ReviewQueue from "./components/ReviewQueue.jsx";
import UploadClaims from "./components/UploadClaims.jsx";

const TABS = ["Review Queue", "Upload Claims", "Stats"];

export default function App() {
  const [tab, setTab] = useState("Review Queue");
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ db_connected: false }));
  }, []);

  useEffect(() => {
    if (tab === "Stats") {
      api.reviewStats().then(setStats).catch(() => {});
      api.modelStatus().then(setModelStatus).catch(() => {});
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
        {tab === "Stats" && <StatsView stats={stats} modelStatus={modelStatus} onTrainDone={() => api.modelStatus().then(setModelStatus).catch(() => {})} />}
      </div>
    </div>
  );
}

function MLModelCard({ modelStatus, onTrainDone }) {
  const [training, setTraining] = useState(false);
  const [trainError, setTrainError] = useState(null);

  if (!modelStatus) return <div className="card"><div className="loading">Loading ML status...</div></div>;

  const handleTrain = async () => {
    setTraining(true);
    setTrainError(null);
    try {
      await api.trainModel();
      onTrainDone?.();
    } catch (err) {
      setTrainError(err.message);
    } finally {
      setTraining(false);
    }
  };

  const { is_trained, labeled_so_far, min_samples_needed, n_samples, cv_auc, trained_at, feature_importances } = modelStatus;
  const progress = Math.min((labeled_so_far / min_samples_needed) * 100, 100);
  const canTrain = labeled_so_far >= min_samples_needed;

  return (
    <div className="card" style={{ borderLeft: `3px solid ${is_trained ? "#16a34a" : "#94a3b8"}` }}>
      <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
        ML Model (Phase 2)
        <span style={{
          fontSize: 11, padding: "2px 8px", borderRadius: 10, fontWeight: 700,
          background: is_trained ? "#dcfce7" : "#f1f5f9",
          color: is_trained ? "#15803d" : "#64748b",
        }}>
          {is_trained ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      {!is_trained && (
        <>
          <div style={{ fontSize: 13, color: "#64748b", marginBottom: 8 }}>
            Train unlocks at {min_samples_needed} labeled reviews.
            Current: <strong>{labeled_so_far}</strong> / {min_samples_needed}
          </div>
          <div style={{ height: 6, background: "#e2e8f0", borderRadius: 3, marginBottom: 10 }}>
            <div style={{ height: "100%", width: `${progress}%`, background: "#3b82f6", borderRadius: 3, transition: "width 0.3s" }} />
          </div>
        </>
      )}

      {is_trained && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12, fontSize: 13 }}>
          <div><span style={{ color: "#64748b" }}>Training samples:</span> <strong>{n_samples}</strong></div>
          <div><span style={{ color: "#64748b" }}>CV AUC:</span> <strong>{cv_auc?.toFixed(3) ?? "—"}</strong></div>
          <div style={{ gridColumn: "1 / -1" }}>
            <span style={{ color: "#64748b" }}>Last trained:</span>{" "}
            <strong>{trained_at ? new Date(trained_at).toLocaleString() : "—"}</strong>
          </div>
        </div>
      )}

      {is_trained && feature_importances?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", marginBottom: 6 }}>Top Features</div>
          {feature_importances.slice(0, 5).map((f) => {
            const maxImp = feature_importances[0].importance;
            const pct = maxImp > 0 ? (f.importance / maxImp) * 100 : 0;
            return (
              <div key={f.name} style={{ marginBottom: 5 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
                  <span>{f.name.replace(/_/g, " ")}</span>
                  <span style={{ color: "#64748b" }}>{f.importance.toFixed(4)}</span>
                </div>
                <div style={{ height: 4, background: "#e2e8f0", borderRadius: 2 }}>
                  <div style={{ height: "100%", width: `${pct}%`, background: "#16a34a", borderRadius: 2 }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {canTrain && (
        <button
          onClick={handleTrain}
          disabled={training}
          style={{
            fontSize: 13, padding: "6px 14px", borderRadius: 6, border: "none", cursor: training ? "not-allowed" : "pointer",
            background: training ? "#94a3b8" : "#16a34a", color: "white", fontWeight: 600,
          }}
        >
          {training ? "Training..." : is_trained ? "Retrain Model" : "Train Model"}
        </button>
      )}
      {trainError && <div style={{ marginTop: 8, fontSize: 12, color: "#dc2626" }}>{trainError}</div>}
    </div>
  );
}

function StatsView({ stats, modelStatus, onTrainDone }) {
  if (!stats) return <div className="loading">Loading stats...</div>;

  return (
    <div>
      <div className="stats-row">
        <div className="stat-card"><div className="num">{stats.total_claims}</div><div className="label">Total Claims</div></div>
        <div className="stat-card"><div className="num">{stats.total_analyzed}</div><div className="label">Analyzed</div></div>
        <div className="stat-card"><div className="num">{stats.total_reviewed}</div><div className="label">Reviewed (Labels)</div></div>
        <div className="stat-card"><div className="num">{stats.label_coverage_pct}%</div><div className="label">Label Coverage</div></div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
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
        </div>
      </div>

      <MLModelCard modelStatus={modelStatus} onTrainDone={onTrainDone} />
    </div>
  );
}
