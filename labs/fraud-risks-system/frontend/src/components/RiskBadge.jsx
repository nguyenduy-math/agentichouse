export default function RiskBadge({ level, score }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span className={`risk-badge ${level || "low"}`}>{level || "—"}</span>
      {score !== undefined && (
        <div className="score-bar" style={{ minWidth: 100 }}>
          <div className="bar">
            <div
              className={`fill ${level}`}
              style={{ width: `${score}%` }}
            />
          </div>
          <span className="val">{score}</span>
        </div>
      )}
    </div>
  );
}
