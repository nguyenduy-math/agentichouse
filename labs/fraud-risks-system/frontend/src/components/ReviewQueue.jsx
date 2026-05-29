import { useEffect, useState } from "react";
import { api } from "../api.js";
import RiskBadge from "./RiskBadge.jsx";
import ClaimDetail from "./ClaimDetail.jsx";

export default function ReviewQueue() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [batchStatus, setBatchStatus] = useState(null);
  const [triggering, setTriggering] = useState(false);

  function load(p = page) {
    setLoading(true);
    api.reviewQueue({ page: p, page_size: 20 })
      .then(setData)
      .finally(() => setLoading(false));
    api.batchStatus().then(setBatchStatus).catch(() => {});
  }

  useEffect(() => { load(); }, [page]);

  async function triggerBatch() {
    setTriggering(true);
    try {
      await api.triggerBatch();
      setTimeout(() => { load(); setTriggering(false); }, 2000);
    } catch {
      setTriggering(false);
    }
  }

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600 }}>Review Queue</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {batchStatus && (
            <span style={{ fontSize: 12, color: "#64748b" }}>
              Last batch: <strong>{batchStatus.status}</strong>
              {batchStatus.claims_processed > 0 && ` · ${batchStatus.claims_processed} processed`}
            </span>
          )}
          <button className="btn btn-primary" onClick={triggerBatch} disabled={triggering}>
            {triggering ? "Running..." : "Run Batch Now"}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {loading ? (
          <div className="loading">Loading...</div>
        ) : !data?.items?.length ? (
          <div className="empty">
            No analyzed claims yet.<br />
            Upload a CSV and run the batch to get started.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Provider</th>
                <th>Amount</th>
                <th>Type</th>
                <th>Risk Score</th>
                <th>Network</th>
                <th>Top Flag</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id} onClick={() => setSelectedId(item.id)}>
                  <td><strong>{item.claim_id}</strong></td>
                  <td>{item.provider_name || "—"}</td>
                  <td>{item.claim_amount ? `$${Number(item.claim_amount).toLocaleString()}` : "—"}</td>
                  <td>{item.claim_type || "—"}</td>
                  <td><RiskBadge level={item.risk_level} score={item.combined_score} /></td>
                  <td>
                    {item.network_risk
                      ? <span className="badge-network">Network Risk</span>
                      : <span style={{ color: "#94a3b8", fontSize: 12 }}>—</span>}
                  </td>
                  <td style={{ fontSize: 12, color: "#475569", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.top_flags?.[0]?.description || "—"}
                  </td>
                  <td>
                    {item.reviewed
                      ? <span className="badge-reviewed">Reviewed</span>
                      : <span className="badge-pending">Pending</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn btn-ghost" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>← Prev</button>
          <span style={{ fontSize: 13, color: "#64748b" }}>Page {page} of {totalPages}</span>
          <button className="btn btn-ghost" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>Next →</button>
        </div>
      )}

      {selectedId && (
        <ClaimDetail
          claimId={selectedId}
          onClose={() => setSelectedId(null)}
          onDecision={() => load()}
        />
      )}
    </div>
  );
}
