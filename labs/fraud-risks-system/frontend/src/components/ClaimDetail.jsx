import { useEffect, useState } from "react";
import { api } from "../api.js";
import RiskBadge from "./RiskBadge.jsx";
import DecisionPanel from "./DecisionPanel.jsx";

export default function ClaimDetail({ claimId, onClose, onDecision }) {
  const [claim, setClaim] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getClaim(claimId).then(setClaim).finally(() => setLoading(false));
  }, [claimId]);

  if (loading) return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="loading">Loading...</div>
      </div>
    </div>
  );

  const analysis = claim?.latest_analysis;
  const llmFlags = analysis?.llm_flags || [];
  const ruleFlags = (analysis?.rule_flags || []).filter(f => !f.type?.startsWith("graph_"));
  const graphFlags = (analysis?.rule_flags || []).filter(f => f.type?.startsWith("graph_"));
  const allFlags = [...llmFlags, ...ruleFlags];

  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <strong>{claim.claim_id}</strong>
            <span style={{ marginLeft: 8, color: "#64748b" }}>{claim.claim_type}</span>
          </div>
          <button className="drawer-close" onClick={onClose}>✕</button>
        </div>

        {analysis && (
          <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <RiskBadge level={analysis.risk_level} score={analysis.combined_score} />
            {analysis.ml_score != null && (
              <span style={{
                fontSize: 12, padding: "3px 8px", borderRadius: 4,
                background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0", fontWeight: 600,
              }}>
                ML {analysis.ml_score}
              </span>
            )}
          </div>
        )}

        <div className="card">
          <div className="card-title">Claim Details</div>
          <div className="detail-grid">
            <div className="detail-field"><label>Provider</label><span>{claim.provider_name || "—"}</span></div>
            <div className="detail-field"><label>Amount</label><span>{claim.claim_amount ? `$${Number(claim.claim_amount).toLocaleString()}` : "—"}</span></div>
            <div className="detail-field"><label>Service Date</label><span>{claim.service_date || "—"}</span></div>
            <div className="detail-field"><label>Submitted</label><span>{claim.submission_date || "—"}</span></div>
            <div className="detail-field"><label>Patient ID</label><span>{claim.patient_id || "—"}</span></div>
            <div className="detail-field"><label>Status</label><span>{claim.status}</span></div>
          </div>
          {claim.diagnosis_codes?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase" }}>Diagnosis (ICD-10): </span>
              {claim.diagnosis_codes.join(", ")}
            </div>
          )}
          {claim.procedure_codes?.length > 0 && (
            <div>
              <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase" }}>Procedure (CPT): </span>
              {claim.procedure_codes.join(", ")}
            </div>
          )}
        </div>

        {claim.claim_narrative && (
          <div className="card">
            <div className="card-title">Claim Narrative</div>
            <div className="narrative-box">{claim.claim_narrative}</div>
          </div>
        )}

        {analysis && (
          <>
            {analysis.llm_explanation && (
              <div className="card">
                <div className="card-title">AI Analysis</div>
                <div className="explanation">{analysis.llm_explanation}</div>
              </div>
            )}

            {graphFlags.length > 0 && (
              <div className="card" style={{ borderLeft: "3px solid #7c3aed" }}>
                <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  Network Signals
                  <span className="badge-network">Graph Detected</span>
                </div>
                <div className="flag-list">
                  {graphFlags.map((f, i) => (
                    <div key={i} className={`flag-item ${f.severity}`} style={{ background: "#f5f3ff", borderLeftColor: "#7c3aed" }}>
                      <div className="flag-type" style={{ color: "#6d28d9" }}>{f.type?.replace(/^graph_/, "").replace(/_/g, " ")} · {f.severity}</div>
                      {f.description}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {allFlags.length > 0 && (
              <div className="card">
                <div className="card-title">Fraud Flags ({allFlags.length})</div>
                <div className="flag-list">
                  {allFlags.map((f, i) => (
                    <div key={i} className={`flag-item ${f.severity}`}>
                      <div className="flag-type">{f.type?.replace(/_/g, " ")} · {f.severity}</div>
                      {f.description}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {claim.status !== "pending" && (
          <DecisionPanel
            claimId={claimId}
            onDecision={(d) => { onDecision?.(d); onClose(); }}
          />
        )}
      </div>
    </div>
  );
}
