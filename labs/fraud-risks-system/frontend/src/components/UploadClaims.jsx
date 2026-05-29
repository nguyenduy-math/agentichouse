import { useRef, useState } from "react";
import { api } from "../api.js";

export default function UploadClaims({ onUploaded }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef();

  async function handleFile(file) {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.uploadClaims(file);
      setResult(data);
      onUploaded?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <div className="card-title">Upload Claims CSV</div>
      <div
        className={`upload-zone ${dragging ? "dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
      >
        {loading ? "Uploading..." : "Drop a CSV file here or click to browse"}
        <input ref={inputRef} type="file" accept=".csv" style={{ display: "none" }} onChange={(e) => handleFile(e.target.files[0])} />
      </div>

      {result && (
        <div style={{ marginTop: 12, color: "#166534", fontSize: 13 }}>
          Inserted <strong>{result.inserted}</strong> claims ({result.skipped} skipped).
        </div>
      )}
      {error && <div style={{ marginTop: 12, color: "#991b1b", fontSize: 13 }}>{error}</div>}

      <div style={{ marginTop: 12, fontSize: 12, color: "#64748b" }}>
        Required column: <code>claim_id</code>. Optional: patient_id, provider_id, provider_name, claim_amount,
        service_date, submission_date, claim_type, diagnosis_codes, procedure_codes, claim_narrative.
        Codes separated by <code>|</code>.
      </div>
    </div>
  );
}
