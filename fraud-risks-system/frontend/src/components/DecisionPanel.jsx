import { useState } from "react";
import { api } from "../api.js";

export default function DecisionPanel({ claimId, onDecision }) {
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState("");

  async function decide(decision) {
    setLoading(true);
    try {
      await api.submitDecision(claimId, { decision, notes: notes || undefined });
      onDecision?.(decision);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <div className="card-title">Investigator Decision</div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Optional notes..."
        style={{ width: "100%", padding: 8, border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 13, minHeight: 64, resize: "vertical", marginBottom: 12 }}
      />
      <div className="decision-panel">
        <button className="btn btn-success" onClick={() => decide("legitimate")} disabled={loading}>
          Legitimate
        </button>
        <button className="btn btn-warning" onClick={() => decide("suspicious")} disabled={loading}>
          Suspicious
        </button>
        <button className="btn btn-danger" onClick={() => decide("confirmed_fraud")} disabled={loading}>
          Confirmed Fraud
        </button>
      </div>
    </div>
  );
}
